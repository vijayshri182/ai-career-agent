"""Education repository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.candidate import Education
from backend.repositories.base import BaseRepository


class EducationRepository(BaseRepository[Education]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Education)

    async def list_ordered(self, candidate_id: UUID) -> list[Education]:
        stmt = (
            select(Education)
            .where(Education.candidate_id == candidate_id)
            .order_by(
                Education.__table__.c.display_order,
                Education.__table__.c.end_date.desc().nullsfirst(),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
