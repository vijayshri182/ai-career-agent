"""Job (posting) schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.models.job import JobStatus


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    company_id: UUID
    source_id: UUID
    external_id: str | None
    url: str
    title: str
    location: str | None
    description: str | None
    status: JobStatus
    posted_at: datetime | None
    closing_at: datetime | None
    first_seen_at: datetime
    last_seen_at: datetime
    created_at: datetime
    updated_at: datetime
