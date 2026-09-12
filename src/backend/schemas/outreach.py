"""Outreach schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.models.outreach import (
    OutreachChannel,
    OutreachRunStatus,
    OutreachStatus,
    ResponseStatus,
)


class OutreachMessageCreate(BaseModel):
    contact_id: UUID
    job_id: UUID | None = None
    application_id: UUID | None = None
    channel: OutreachChannel = OutreachChannel.EMAIL
    subject: str | None = Field(default=None, max_length=150)
    body: str | None = None


class OutreachMessageUpdate(BaseModel):
    subject: str = Field(max_length=150)
    body: str
    change_reason: str | None = None


class OutreachFollowUpCreate(BaseModel):
    parent_message_id: UUID
    subject: str | None = Field(default=None, max_length=150)
    body: str | None = None


class OutreachSubmitRequest(BaseModel):
    summary: str | None = None


class OutreachRespondRequest(BaseModel):
    note: str | None = None


class OutreachSuppressRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class OutreachMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    contact_id: UUID
    job_id: UUID | None
    application_id: UUID | None
    channel: OutreachChannel
    subject: str
    body: str
    status: OutreachStatus
    response_status: ResponseStatus
    is_follow_up: bool
    parent_id: UUID | None
    approval_id: str | None
    rules_version: str
    fact_sources: list[dict[str, object]]
    sent_at: datetime | None
    responded_at: datetime | None
    provider_message_id: str | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class OutreachMessageVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    message_id: UUID
    version_number: int
    subject: str
    body: str
    is_generated: bool
    change_reason: str | None
    fact_sources: list[dict[str, object]]
    created_by: str | None
    created_at: datetime


class OutreachRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    message_id: UUID
    status: OutreachRunStatus
    attempt_count: int
    max_attempts: int
    next_retry_at: datetime | None
    last_error: str | None
    result_metadata: dict[str, object]
    started_at: datetime | None
    sent_at: datetime | None
    finished_at: datetime | None
    provider_message_id: str | None
    created_at: datetime
    updated_at: datetime


class OutreachMessageDetail(OutreachMessageRead):
    versions: list[OutreachMessageVersionRead] = []
    runs: list[OutreachRunRead] = []


class OutreachMessageListResponse(BaseModel):
    items: list[OutreachMessageRead]
    total: int


class OutreachRunListResponse(BaseModel):
    items: list[OutreachRunRead]
    total: int


class OutreachSubmitResponse(BaseModel):
    message_id: UUID
    status: OutreachStatus
    approval_id: str | None
    approval_required: bool


class OutreachStatusSummary(BaseModel):
    total: int
    draft: int
    pending_approval: int
    approved: int
    sent: int
    failed: int
    cancelled: int
    responded: int
    sent_today: int
    daily_limit: int
