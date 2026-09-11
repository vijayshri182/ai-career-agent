"""Job deduplication classification."""

from dataclasses import dataclass
from uuid import UUID

from backend.repositories.job import JobRepository
from backend.services.normalization import NormalizedJob


@dataclass
class DedupDecision:
    """Result of classifying one normalized posting against existing jobs."""

    job: NormalizedJob
    is_new: bool
    existing_key: str | None = None


class JobDedupService:
    """Classify normalized postings as new or duplicate.

    Precedence (most specific wins): exact URL → (company, external_id) →
    content hash. Company IDs are resolved upstream and passed in as a mapping
    keyed by normalized domain (or name if no domain). Lookups are batched so a
    single pass classifies all postings from a source run.
    """

    def __init__(self, job_repo: JobRepository) -> None:
        self.job_repo = job_repo

    async def classify(
        self,
        candidate_id: UUID,
        postings: list[NormalizedJob],
        company_id_map: dict[str, UUID] | None = None,
    ) -> list[DedupDecision]:
        if not postings:
            return []

        company_map = company_id_map or {}
        existing_urls, existing_company_external, existing_hashes = await self.job_repo.find_existing(
            candidate_id,
            urls={p.url for p in postings},
            company_external={
                (company_id, ext_id)
                for p in postings
                if (company_id := self._resolve_company_id(p, company_map)) is not None
                for ext_id in [p.external_id]
                if ext_id is not None
            },
            content_hashes={p.content_hash for p in postings},
        )

        decisions: list[DedupDecision] = []
        for posting in postings:
            if posting.url in existing_urls:
                decisions.append(DedupDecision(posting, False, "url"))
                continue
            resolved = self._resolve_company_id(posting, company_map)
            if (
                resolved is not None
                and posting.external_id is not None
                and (resolved, posting.external_id) in existing_company_external
            ):
                decisions.append(DedupDecision(posting, False, "company_external_id"))
                continue
            if posting.content_hash in existing_hashes:
                decisions.append(DedupDecision(posting, False, "content_hash"))
                continue
            decisions.append(DedupDecision(posting, True, None))
        return decisions

    @staticmethod
    def _resolve_company_id(
        posting: NormalizedJob, company_map: dict[str, UUID]
    ) -> UUID | None:
        domain = posting.company_domain
        if domain and domain in company_map:
            return company_map[domain]
        return None
