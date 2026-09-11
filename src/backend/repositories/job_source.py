"""Job source repository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.job_source import JobSource
from backend.repositories.base import BaseRepository


class JobSourceRepository(BaseRepository[JobSource]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, JobSource)

    async def list_for_candidate(self, candidate_id: UUID) -> list[JobSource]:
        stmt = (
            select(JobSource)
            .where(JobSource.candidate_id == candidate_id)
            .order_by(JobSource.__table__.c.name)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_candidate(self, source_id: UUID, candidate_id: UUID) -> JobSource | None:
        stmt = select(JobSource).where(
            JobSource.id == source_id, JobSource.candidate_id == candidate_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_enabled(self) -> list[JobSource]:
        stmt = select(JobSource).where(JobSource.is_enabled.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
