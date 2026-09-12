"""Automation run repository."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.automation_run import AutomationRun, AutomationRunStatus
from backend.repositories.base import BaseRepository

ACTIVE_STATUSES = (
    AutomationRunStatus.PENDING,
    AutomationRunStatus.RUNNING,
    AutomationRunStatus.PAUSED_HUMAN_ACTION,
)


class AutomationRunRepository(BaseRepository[AutomationRun]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AutomationRun)

    async def get_for_candidate(self, run_id: UUID, candidate_id: UUID) -> AutomationRun | None:
        stmt = select(AutomationRun).where(
            AutomationRun.id == run_id,
            AutomationRun.candidate_id == candidate_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_for_application(self, application_id: UUID) -> AutomationRun | None:
        stmt = (
            select(AutomationRun)
            .where(AutomationRun.application_id == application_id)
            .order_by(AutomationRun.__table__.c.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def get_active_for_application(self, application_id: UUID) -> AutomationRun | None:
        stmt = (
            select(AutomationRun)
            .where(AutomationRun.application_id == application_id)
            .where(AutomationRun.status.in_(ACTIVE_STATUSES))
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def list_for_candidate(
        self,
        candidate_id: UUID,
        *,
        status: AutomationRunStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AutomationRun]:
        stmt = select(AutomationRun).where(AutomationRun.candidate_id == candidate_id)
        if status is not None:
            stmt = stmt.where(AutomationRun.status == status)
        stmt = (
            stmt.order_by(AutomationRun.__table__.c.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_for_candidate(
        self, candidate_id: UUID, status: AutomationRunStatus | None = None
    ) -> int:
        stmt = select(func.count()).select_from(AutomationRun).where(
            AutomationRun.candidate_id == candidate_id
        )
        if status is not None:
            stmt = stmt.where(AutomationRun.status == status)
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_by_status(self, candidate_id: UUID) -> dict[AutomationRunStatus, int]:
        stmt = (
            select(AutomationRun.status, func.count())
            .where(AutomationRun.candidate_id == candidate_id)
            .group_by(AutomationRun.status)
        )
        result = await self.session.execute(stmt)
        return {status: int(count) for status, count in result.all()}
