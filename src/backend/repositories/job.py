"""Job posting repository with deduplication lookups."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.job import Job, JobStatus
from backend.repositories.base import BaseRepository


class JobRepository(BaseRepository[Job]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Job)

    async def list_for_candidate(
        self,
        candidate_id: UUID,
        *,
        status: JobStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Job]:
        stmt = select(Job).where(Job.candidate_id == candidate_id)
        if status is not None:
            stmt = stmt.where(Job.status == status)
        stmt = stmt.order_by(Job.__table__.c.first_seen_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_candidate(self, job_id: UUID, candidate_id: UUID) -> Job | None:
        stmt = select(Job).where(Job.id == job_id, Job.candidate_id == candidate_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_existing(
        self,
        candidate_id: UUID,
        urls: set[str],
        company_external: set[tuple[UUID, str]],
        content_hashes: set[str],
    ) -> tuple[set[str], set[tuple[UUID, str]], set[str]]:
        """Return which dedup keys already exist for this candidate.

        Returns ``(existing_urls, existing_company_external, existing_hashes)``.
        Empty inputs short-circuit so we never build huge IN clauses.
        """
        existing_urls: set[str] = set()
        if urls:
            stmt = select(Job.url).where(
                Job.candidate_id == candidate_id, Job.url.in_(urls)
            )
            result = await self.session.execute(stmt)
            existing_urls = set(result.scalars().all())

        existing_company_external: set[tuple[UUID, str]] = set()
        if company_external:
            company_ids = [cid for cid, _ in company_external]
            external_ids = [ext for _, ext in company_external]
            external_id_col = Job.__table__.c.external_id
            stmt = select(Job.company_id, Job.external_id).where(
                Job.candidate_id == candidate_id,
                Job.company_id.in_(company_ids),
                external_id_col.in_(external_ids),
            )
            result = await self.session.execute(stmt)
            rows = result.all()
            existing_company_external = {
                (row[0], row[1]) for row in rows if row[1] is not None
            }

        existing_hashes: set[str] = set()
        if content_hashes:
            stmt = select(Job.content_hash).where(
                Job.candidate_id == candidate_id, Job.content_hash.in_(content_hashes)
            )
            result = await self.session.execute(stmt)
            existing_hashes = set(result.scalars().all())

        return existing_urls, existing_company_external, existing_hashes

    async def mark_expired(
        self,
        candidate_id: UUID,
        now: datetime,
        statuses: Sequence[JobStatus] = (JobStatus.DISCOVERED, JobStatus.VERIFIED),
    ) -> int:
        stmt = (
            update(Job)
            .where(
                Job.candidate_id == candidate_id,
                Job.__table__.c.closing_at.is_not(None),
                Job.__table__.c.closing_at < now,
                Job.status.in_(statuses),
            )
            .values(status=JobStatus.EXPIRED, updated_at=now)
        )
        result = await self.session.execute(stmt)
        return result.rowcount or 0

    async def find_identical(
        self,
        candidate_id: UUID,
        *,
        url: str | None,
        company_id: UUID | None,
        external_id: str | None,
        content_hash: str | None,
    ) -> Job | None:
        """Return an existing job matching the given posting, by strongest key.

        Precedence is exact URL, then (company, external_id), then content
        hash. Returns the first match, mirroring the precedence documented in
        the dedup service.
        """
        if url:
            job = await self._first_where(candidate_id, Job.url == url)
            if job is not None:
                return job
        if company_id is not None and external_id is not None:
            job = await self._first_where(
                candidate_id, Job.company_id == company_id, Job.external_id == external_id
            )
            if job is not None:
                return job
        if content_hash:
            job = await self._first_where(candidate_id, Job.content_hash == content_hash)
            if job is not None:
                return job
        return None

    async def _first_where(self, candidate_id: UUID, *criteria: object) -> Job | None:
        stmt = select(Job).where(Job.candidate_id == candidate_id, *criteria).limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()
