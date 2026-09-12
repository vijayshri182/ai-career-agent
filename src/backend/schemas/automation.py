"""Application automation schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.models.automation_run import AutomationRunStatus


class AutomationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    application_id: UUID
    provider_id: UUID | None
    challenge_id: UUID | None
    workflow_id: UUID | None
    status: AutomationRunStatus
    attempt_count: int
    max_attempts: int
    next_retry_at: datetime | None
    last_error: str | None
    context_metadata: dict[str, object]
    result_metadata: dict[str, object]
    started_at: datetime
    submitted_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AutomationRunListResponse(BaseModel):
    items: list[AutomationRunRead]
    total: int


class AutomationStatusSummary(BaseModel):
    total: int
    in_progress: int
    paused_human_action: int
    submitted: int
    failed: int
