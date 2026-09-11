"""Job freshness marking (closing-date expiration)."""

from datetime import UTC, datetime

from backend.repositories.job import JobRepository


class JobFreshnessService:
    """Mark expired jobs whose ``closing_at`` date has passed.

    Only `DISCOVERED` / `VERIFIED` postings are expired; posts that are
    already `EXPIRED` or `REJECTED` are untouched. The check is idempotent.
    """

    def __init__(self, job_repo: JobRepository, *, now: datetime | None = None) -> None:
        self.job_repo = job_repo
        self._now = now

    @property
    def now(self) -> datetime:
        return self._now or datetime.now(UTC)

    async def mark_expired(self, candidate_id: str | object) -> int:  # noqa: B027
        """Return the number of newly-expired postings (0 = idempotent)."""
        from uuid import UUID

        cid = UUID(str(candidate_id)) if not isinstance(candidate_id, UUID) else candidate_id
        return await self.job_repo.mark_expired(cid, self.now)
