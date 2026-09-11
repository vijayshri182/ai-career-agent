"""Agent task schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.models.agent_task import AgentTaskStatus


class AgentTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID | None
    task_type: str
    status: AgentTaskStatus
    retry_count: int
    max_retries: int
    scheduled_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    result_metadata: dict[str, object]
    created_at: datetime
