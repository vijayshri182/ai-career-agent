"""Certification repository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.candidate import Certification
from backend.repositories.base import BaseRepository


class CertificationRepository(BaseRepository[Certification]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Certification)

    async def list_ordered(self, candidate_id: UUID) -> list[Certification]:
        stmt = (
            select(Certification)
            .where(Certification.candidate_id == candidate_id)
            .order_by(
                Certification.__table__.c.display_order,
                Certification.__table__.c.issue_date.desc().nullslast(),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
