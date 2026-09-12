"""Job match repository."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.job_match import JobMatch, JobMatchStatus
from backend.repositories.base import BaseRepository


class JobMatchRepository(BaseRepository[JobMatch]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, JobMatch)

    async def get_for_job(self, candidate_id: UUID, job_id: UUID) -> JobMatch | None:
        stmt = select(JobMatch).where(
            JobMatch.candidate_id == candidate_id, JobMatch.job_id == job_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(self, candidate_id: UUID, job_id: UUID, **data: object) -> JobMatch:
        """Idempotently create or update the match row for a (candidate, job)."""
        existing = await self.get_for_job(candidate_id, job_id)
        if existing is not None:
            return await self.update(existing, **data)
        return await self.create(candidate_id=candidate_id, job_id=job_id, **data)

    async def list_for_candidate(
        self,
        candidate_id: UUID,
        *,
        is_match: bool | None = None,
        status: JobMatchStatus | None = None,
        min_score: float | None = None,
        sort: str = "score",
        limit: int = 50,
        offset: int = 0,
    ) -> list[JobMatch]:
        stmt = select(JobMatch).where(JobMatch.candidate_id == candidate_id)
        if is_match is not None:
            stmt = stmt.where(JobMatch.is_match == is_match)
        if status is not None:
            stmt = stmt.where(JobMatch.status == status)
        if min_score is not None:
            stmt = stmt.where(JobMatch.__table__.c.score >= min_score)
        if sort == "recent":
            stmt = stmt.order_by(JobMatch.__table__.c.evaluated_at.desc())
        else:
            stmt = stmt.order_by(JobMatch.__table__.c.score.desc())
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_candidate(
        self,
        candidate_id: UUID,
        *,
        is_match: bool | None = None,
        status: JobMatchStatus | None = None,
        min_score: float | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(JobMatch).where(JobMatch.candidate_id == candidate_id)
        if is_match is not None:
            stmt = stmt.where(JobMatch.is_match == is_match)
        if status is not None:
            stmt = stmt.where(JobMatch.status == status)
        if min_score is not None:
            stmt = stmt.where(JobMatch.__table__.c.score >= min_score)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())
