"""Audit trail read schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: str
    actor_id: UUID | None
    candidate_id: UUID | None
    entity_type: str | None
    entity_id: UUID | None
    result: str
    request_id: str | None
    event_metadata: dict[str, object]
    details: str | None
    created_at: datetime


class AuditEventListResponse(BaseModel):
    items: list[AuditEventRead]
    total: int
