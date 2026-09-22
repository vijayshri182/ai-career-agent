"""Recruiter signal repositories."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.recruiter_signal import (
    RecruiterSignal,
    RecruiterSignalStatus,
    RecruiterSignalType,
)
from backend.repositories.base import BaseRepository


class RecruiterSignalRepository(BaseRepository[RecruiterSignal]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RecruiterSignal)

    async def get_for_candidate(self, signal_id: UUID, candidate_id: UUID) -> RecruiterSignal | None:
        stmt = select(RecruiterSignal).where(
            RecruiterSignal.id == signal_id,
            RecruiterSignal.candidate_id == candidate_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def find_by_identity(
        self, candidate_id: UUID, signal_identity: str
    ) -> RecruiterSignal | None:
        stmt = select(RecruiterSignal).where(
            RecruiterSignal.candidate_id == candidate_id,
            RecruiterSignal.signal_identity == signal_identity,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_candidate(
        self,
        candidate_id: UUID,
        *,
        status: RecruiterSignalStatus | None = None,
        signal_type: RecruiterSignalType | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RecruiterSignal]:
        stmt = select(RecruiterSignal).where(RecruiterSignal.candidate_id == candidate_id)
        if status is not None:
            stmt = stmt.where(RecruiterSignal.status == status)
        if signal_type is not None:
            stmt = stmt.where(RecruiterSignal.signal_type == signal_type)
        stmt = (
            stmt.order_by(RecruiterSignal.__table__.c.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_for_job(
        self, candidate_id: UUID, job_id: UUID
    ) -> list[RecruiterSignal]:
        stmt = select(RecruiterSignal).where(
            RecruiterSignal.candidate_id == candidate_id,
            RecruiterSignal.job_id == job_id,
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_for_candidate(
        self,
        candidate_id: UUID,
        *,
        status: RecruiterSignalStatus | None = None,
        signal_type: RecruiterSignalType | None = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(RecruiterSignal)
            .where(RecruiterSignal.candidate_id == candidate_id)
        )
        if status is not None:
            stmt = stmt.where(RecruiterSignal.status == status)
        if signal_type is not None:
            stmt = stmt.where(RecruiterSignal.signal_type == signal_type)
        return int((await self.session.execute(stmt)).scalar_one())
