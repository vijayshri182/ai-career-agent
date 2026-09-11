"""Workflow run schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.models.workflow_run import WorkflowStatus


class WorkflowRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    provider_id: UUID
    workflow_type: str
    status: WorkflowStatus
    attempt_count: int
    max_attempts: int
    context_metadata: dict[str, object]
    started_at: datetime
    paused_at: datetime | None
    resumed_at: datetime | None
    finished_at: datetime | None
    expires_at: datetime | None


class WorkflowResumeInput(BaseModel):
    resume_token: UUID | None = None
