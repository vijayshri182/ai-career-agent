"""Agent task repository."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.agent_task import AgentTask, AgentTaskStatus
from backend.repositories.base import BaseRepository


class AgentTaskRepository(BaseRepository[AgentTask]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AgentTask)

    async def create_task(
        self,
        task_type: str,
        *,
        candidate_id: UUID | None = None,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        max_retries: int = 2,
        scheduled_at: datetime | None = None,
    ) -> AgentTask:
        return await self.create(
            task_type=task_type,
            candidate_id=candidate_id,
            entity_type=entity_type,
            entity_id=entity_id,
            max_retries=max_retries,
            scheduled_at=scheduled_at,
        )

    async def mark_running(self, task: AgentTask, started_at: datetime) -> AgentTask:
        return await self.update(
            task, status=AgentTaskStatus.RUNNING, started_at=started_at, retry_count=task.retry_count + 1
        )

    async def mark_success(self, task: AgentTask, finished_at: datetime, **result: Any) -> AgentTask:
        metadata = dict(task.result_metadata or {})
        metadata.update(result)
        return await self.update(
            task, status=AgentTaskStatus.SUCCESS, finished_at=finished_at, result_metadata=metadata
        )

    async def mark_failed(self, task: AgentTask, finished_at: datetime, error: str) -> AgentTask:
        return await self.update(
            task, status=AgentTaskStatus.FAILED, finished_at=finished_at, error_message=error
        )

    async def list_for_candidate(
        self,
        candidate_id: UUID,
        *,
        task_type: str | None = None,
        limit: int = 50,
    ) -> list[AgentTask]:
        stmt = select(AgentTask).where(AgentTask.candidate_id == candidate_id)
        if task_type is not None:
            stmt = stmt.where(AgentTask.task_type == task_type)
        stmt = stmt.order_by(AgentTask.__table__.c.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
