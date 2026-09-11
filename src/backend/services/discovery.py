"""Job discovery orchestrator.

Coordinates a single discovery run: picks enabled sources, checks robots.txt
and crawl rate-limits, fetches/normalizes content, deduplicates against
existing jobs, stores raw extractions, and marks expired postings. All network
I/O for one run shares a single httpx client (so crawling is pipelined and the
client is always closed).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from backend.core.config import Settings
from backend.core.exceptions import NotFoundError, ValidationError
from backend.models.job_source import JobSource
from backend.models.raw_job_extraction import RawExtractionStatus
from backend.repositories.agent_task import AgentTaskRepository
from backend.repositories.audit import AuditRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.company import CompanyRepository
from backend.repositories.job import JobRepository
from backend.repositories.job_source import JobSourceRepository
from backend.repositories.raw_job_extraction import RawJobExtractionRepository
from backend.schemas.agent_task import AgentTaskRead
from backend.schemas.discovery import DiscoveryRunResult, SourceRunOutcome
from backend.services.adapters.base import JobSourceAdapter
from backend.services.freshness import JobFreshnessService
from backend.services.normalization import JobNormalizer, NormalizedJob
from backend.services.robots import RobotsTxt, parse_robots_txt, request_path_for, robots_url_for


@dataclass
class _RunAccumulator:
    sources_attempted: int = 0
    sources_succeeded: int = 0
    fetched: int = 0
    new_jobs: int = 0
    duplicate_jobs: int = 0
    marked_expired: int = 0
    outcomes: list[SourceRunOutcome] = field(default_factory=list)
    company_id_map: dict[str, UUID] = field(default_factory=dict)


class DiscoveryService:
    def __init__(
        self,
        *,
        candidate_repo: CandidateRepository,
        source_repo: JobSourceRepository,
        company_repo: CompanyRepository,
        job_repo: JobRepository,
        extraction_repo: RawJobExtractionRepository,
        task_repo: AgentTaskRepository,
        audit_repo: AuditRepository,
        adapter_factory: Callable[[httpx.AsyncClient], JobSourceAdapter],
        client_factory: Callable[[], httpx.AsyncClient],
        normalizer: JobNormalizer,
        settings: Settings,
    ) -> None:
        self._candidate_repo = candidate_repo
        self._source_repo = source_repo
        self._company_repo = company_repo
        self._job_repo = job_repo
        self._extraction_repo = extraction_repo
        self._task_repo = task_repo
        self._audit_repo = audit_repo
        self._adapter_factory = adapter_factory
        self._client_factory = client_factory
        self._normalizer = normalizer
        self._settings = settings

    async def run_discovery(
        self, candidate_id: UUID, user_id: UUID, source_ids: list[UUID] | None = None
    ) -> DiscoveryRunResult:
        candidate = await self._candidate_repo.get_for_user_or_404(candidate_id, user_id)
        sources = await self._resolve_sources(candidate_id, source_ids)
        now = datetime.now(UTC)
        task = await self._task_repo.create_task(
            task_type="job_discovery",
            candidate_id=candidate.id,
            entity_type="candidate",
            entity_id=candidate.id,
            scheduled_at=now,
        )
        task = await self._task_repo.mark_running(task, started_at=now)
        acc = _RunAccumulator()
        robots_cache: dict[str, RobotsTxt | None] = {}
        rate_limiter = _CrawlRateLimiter()
        client = self._client_factory()
        adapter = self._adapter_factory(client)

        try:
            for source in sources:
                outcome = await self._process_source(
                    candidate_id, source, acc, robots_cache, rate_limiter, client, adapter
                )
                acc.outcomes.append(outcome)
                acc.sources_attempted += 1
                if outcome.ok:
                    acc.sources_succeeded += 1
                await self._source_repo.flush()
            acc.marked_expired = await JobFreshnessService(self._job_repo).mark_expired(candidate_id)
            await self._audit_repo.log(
                event_type="DISCOVERY_RUN_COMPLETED",
                actor_id=user_id,
                candidate_id=candidate_id,
                entity_type="candidate",
                entity_id=candidate_id,
                metadata={
                    "sources_attempted": acc.sources_attempted,
                    "new_jobs": acc.new_jobs,
                    "marked_expired": acc.marked_expired,
                },
            )
            task = await self._task_repo.mark_success(
                task,
                finished_at=datetime.now(UTC),
                sources_attempted=acc.sources_attempted,
                sources_succeeded=acc.sources_succeeded,
                new_jobs=acc.new_jobs,
                duplicate_jobs=acc.duplicate_jobs,
                marked_expired=acc.marked_expired,
            )
        except Exception as exc:  # noqa: BLE001
            task = await self._task_repo.mark_failed(
                task, finished_at=datetime.now(UTC), error=f"{type(exc).__name__}: {exc}"
            )
        finally:
            await client.aclose()
            await self._source_repo.flush()
            await self._extraction_repo.flush()
            await self._task_repo.flush()

        return DiscoveryRunResult(
            task=AgentTaskRead.model_validate(task),
            candidate_id=candidate_id,
            sources_attempted=acc.sources_attempted,
            sources_succeeded=acc.sources_succeeded,
            fetched=acc.fetched,
            new_jobs=acc.new_jobs,
            duplicate_jobs=acc.duplicate_jobs,
            marked_expired=acc.marked_expired,
            source_outcomes=acc.outcomes,
        )

    async def _resolve_sources(
        self, candidate_id: UUID, source_ids: list[UUID] | None
    ) -> list[JobSource]:
        if source_ids:
            sources: list[JobSource] = []
            for sid in source_ids:
                source = await self._source_repo.get_for_candidate(sid, candidate_id)
                if source is None:
                    raise NotFoundError("Job source not found")
                sources.append(source)
            return [s for s in sources if s.is_enabled]
        all_sources = await self._source_repo.list_for_candidate(candidate_id)
        return [s for s in all_sources if s.is_enabled]

    async def _process_source(
        self,
        candidate_id: UUID,
        source: JobSource,
        acc: _RunAccumulator,
        robots_cache: dict[str, RobotsTxt | None],
        rate_limiter: _CrawlRateLimiter,
        client: httpx.AsyncClient,
        adapter: JobSourceAdapter,
    ) -> SourceRunOutcome:
        outcome_error: str | None = None
        try:
            robots = await self._check_robots(source, robots_cache, client)
            if robots is not None and not robots.allows(request_path_for(source.base_url)):
                outcome_error = "disallowed by robots.txt"
            else:
                await rate_limiter.wait_for(source)
                fetch_result = await adapter.fetch(source)
                source.last_run_at = datetime.now(UTC)
                if fetch_result.error:
                    outcome_error = fetch_result.error
                else:
                    source.last_error = None
                    source.last_success_at = datetime.now(UTC)
                    acc.fetched += len(fetch_result.jobs)
                    source_new, source_dup = await self._store_jobs(candidate_id, source, fetch_result.jobs, acc)
                    return SourceRunOutcome(
                        source_id=source.id,
                        source_name=source.name,
                        ok=True,
                        jobs_fetched=len(fetch_result.jobs),
                        new_jobs=source_new,
                        duplicate_jobs=source_dup,
                        extracted=len(fetch_result.jobs),
                    )
        except ValidationError as exc:
            outcome_error = str(exc)
        except NotFoundError:
            raise
        except Exception as exc:  # noqa: BLE001
            outcome_error = f"{type(exc).__name__}: {exc}"

        source.last_run_at = datetime.now(UTC)
        source.last_error = outcome_error
        return SourceRunOutcome(
            source_id=source.id,
            source_name=source.name,
            ok=False,
            error=outcome_error,
        )

    async def _store_jobs(
        self,
        candidate_id: UUID,
        source: JobSource,
        postings: list[NormalizedJob],
        acc: _RunAccumulator,
    ) -> tuple[int, int]:
        new_count = 0
        dup_count = 0
        for posting in postings:
            await self._store_raw_extraction(candidate_id, source, posting.url, posting.content_hash)
            if posting.closing_at is not None and posting.closing_at < datetime.now(UTC):
                continue
            company_id = await self._company_for(posting, acc)
            if company_id is None:
                continue
            existing = await self._job_repo.find_identical(
                candidate_id,
                url=posting.url,
                company_id=company_id,
                external_id=posting.external_id,
                content_hash=posting.content_hash,
            )
            if existing:
                dup_count += 1
                acc.duplicate_jobs += 1
                continue
            now = datetime.now(UTC)
            await self._job_repo.create(
                candidate_id=candidate_id,
                company_id=company_id,
                source_id=source.id,
                external_id=posting.external_id,
                url=posting.url,
                title=posting.title,
                location=posting.location,
                description=posting.description,
                content_hash=posting.content_hash,
                posted_at=posting.posted_at,
                closing_at=posting.closing_at,
                first_seen_at=now,
                last_seen_at=now,
            )
            new_count += 1
            acc.new_jobs += 1
        return new_count, dup_count

    async def _company_for(self, posting: NormalizedJob, acc: _RunAccumulator) -> UUID | None:
        domain = posting.company_domain
        if domain in acc.company_id_map:
            return acc.company_id_map[domain]
        company = (
            await self._company_repo.find_by_domain(domain)
            if domain
            else None
        )
        if company is None:
            company = await self._company_repo.get_or_create_by_domain(
                name=posting.company_name or posting.company_domain or "Unknown Employer",
                domain=domain,
            )
        acc.company_id_map[domain or ""] = company.id
        return company.id

    async def _check_robots(
        self,
        source: JobSource,
        cache: dict[str, RobotsTxt | None],
        client: httpx.AsyncClient,
    ) -> RobotsTxt | None:
        origin = _origin_key(source.base_url)
        if origin in cache:
            return cache[origin]
        robots_url = robots_url_for(source.base_url)
        try:
            response = await client.get(
                robots_url,
                headers={"User-Agent": self._settings.crawl_user_agent},
                timeout=self._settings.crawl_timeout_seconds,
            )
            if response.status_code in {404, 405, 503}:
                cache[origin] = None
                return None
            response.raise_for_status()
            robots = parse_robots_txt(response.text, self._settings.crawl_user_agent)
            cache[origin] = robots
            return robots
        except Exception:  # noqa: BLE001
            cache[origin] = None
            return None

    async def _store_raw_extraction(
        self,
        candidate_id: UUID,
        source: JobSource,
        fetch_url: str,
        content_hash: str | None,
    ) -> None:
        await self._extraction_repo.create(
            candidate_id=candidate_id,
            source_id=source.id,
            fetch_url=fetch_url,
            fetched_at=source.last_run_at or datetime.now(UTC),
            status=RawExtractionStatus.PARSED,
            raw_payload={"content_hash": content_hash} if content_hash else None,
            content_hash=content_hash,
        )


class _CrawlRateLimiter:
    def __init__(self) -> None:
        self._last_request: dict[str, datetime] = {}

    async def wait_for(self, source: JobSource) -> None:
        config = source.crawl_config or {}
        rpm = config.get("requests_per_minute")
        if not isinstance(rpm, (int, float)) or rpm < 1:
            rpm = 10
        min_interval = 60.0 / float(rpm)
        key = _origin_key(source.base_url)
        last = self._last_request.get(key)
        now = datetime.now(UTC)
        if last is not None:
            elapsed = (now - last).total_seconds()
            wait = min_interval - elapsed
            if wait > 0:
                await asyncio.sleep(wait)
        self._last_request[key] = datetime.now(UTC)


def _origin_key(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else url
