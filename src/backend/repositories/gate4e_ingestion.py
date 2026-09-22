"""Gate 4E ingestion record repository."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.gate4e_ingestion import Gate4eIngestion, Gate4eProcessingStatus
from backend.repositories.base import BaseRepository


class Gate4eIngestionRepository(BaseRepository[Gate4eIngestion]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Gate4eIngestion)

    async def find_by_identity(
        self, candidate_id: UUID, ingestion_identity: str
    ) -> Gate4eIngestion | None:
        stmt = select(Gate4eIngestion).where(
            Gate4eIngestion.candidate_id == candidate_id,
            Gate4eIngestion.ingestion_identity == ingestion_identity,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def count_for_candidate(self, candidate_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Gate4eIngestion)
            .where(Gate4eIngestion.candidate_id == candidate_id)
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def list_for_candidate(
        self,
        candidate_id: UUID,
        *,
        status: Gate4eProcessingStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Gate4eIngestion]:
        stmt = select(Gate4eIngestion).where(Gate4eIngestion.candidate_id == candidate_id)
        if status is not None:
            stmt = stmt.where(Gate4eIngestion.processing_status == status)
        stmt = (
            stmt.order_by(Gate4eIngestion.__table__.c.created_at.desc()).limit(limit).offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
