"""Workflow run repository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import NotFoundError
from backend.models.workflow_run import WorkflowRun, WorkflowStatus
from backend.repositories.base import BaseRepository


class WorkflowRunRepository(BaseRepository[WorkflowRun]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, WorkflowRun)

    async def get_by_token(self, token: UUID) -> WorkflowRun | None:
        stmt = select(WorkflowRun).where(WorkflowRun.resume_token == token)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_by_candidate(
        self, candidate_id: UUID, status: WorkflowStatus | None = None
    ) -> list[WorkflowRun]:
        stmt = select(WorkflowRun).where(WorkflowRun.candidate_id == candidate_id)
        if status is not None:
            stmt = stmt.where(WorkflowRun.status == status)
        stmt = stmt.order_by(WorkflowRun.started_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def latest_for_provider(self, provider_id: UUID) -> WorkflowRun | None:
        stmt = (
            select(WorkflowRun)
            .where(WorkflowRun.provider_id == provider_id)
            .order_by(WorkflowRun.started_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_for_candidate_or_404(
        self, run_id: UUID, candidate_id: UUID
    ) -> WorkflowRun:
        run = await self.get(run_id)
        if run is None or run.candidate_id != candidate_id:
            raise NotFoundError("Workflow not found")
        return run
