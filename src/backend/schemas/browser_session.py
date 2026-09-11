"""Browser session schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.models.browser_session import BrowserSessionStatus


class BrowserSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    provider_id: UUID
    status: BrowserSessionStatus
    storage_reference: str | None
    external_session_id: str | None
    last_seen_at: datetime | None
    closed_at: datetime | None
    created_at: datetime


class BrowserSessionCreate(BaseModel):
    provider_id: UUID
    storage_reference: str | None = None
    external_session_id: str | None = None
