"""Experience repository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.candidate import Experience
from backend.repositories.base import BaseRepository


class ExperienceRepository(BaseRepository[Experience]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Experience)

    async def list_ordered(self, candidate_id: UUID) -> list[Experience]:
        stmt = (
            select(Experience)
            .where(Experience.candidate_id == candidate_id)
            .order_by(
                Experience.__table__.c.display_order,
                Experience.__table__.c.start_date.desc(),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
