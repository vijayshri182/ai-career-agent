"""Approval workflow schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.models.approval import ApprovalDecisionType, ApprovalKind, ApprovalStatus


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    kind: ApprovalKind
    status: ApprovalStatus
    target_type: str
    target_id: UUID
    application_id: UUID | None
    autonomy_level: int
    summary: str | None
    context: dict[str, object]
    decided_by: UUID | None
    decided_at: datetime | None
    decision_type: ApprovalDecisionType | None
    decision_note: str | None
    snoozed_until: datetime | None
    created_at: datetime
    updated_at: datetime


class ApprovalDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    approval_id: UUID
    actor_id: UUID | None
    decision_type: ApprovalDecisionType
    note: str | None
    decided_at: datetime


class ApprovalListResponse(BaseModel):
    items: list[ApprovalRead]
    total: int


class ApprovalDetailRead(ApprovalRead):
    decisions: list[ApprovalDecisionRead]


class ApprovalRequestResponse(BaseModel):
    approval: ApprovalRead


class ApprovalDecisionRequest(BaseModel):
    note: str | None = None


class ApprovalSnoozeRequest(BaseModel):
    until: datetime
    note: str | None = None
