"""Recruiter contact schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.models.recruiter_contact import ContactType


class RecruiterContactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    company_id: UUID
    job_id: UUID | None
    source_id: UUID
    full_name: str
    role_title: str
    public_profile_url: str
    email: str | None
    confidence_score: int
    contact_type: ContactType
    is_suppressed: bool
    verification_details: dict[str, object]
    created_at: datetime
    updated_at: datetime


class RecruiterContactListResponse(BaseModel):
    items: list[RecruiterContactRead]
    total: int


class DiscoverContactsResponse(BaseModel):
    found: int
    created: int
    existing_skipped: int
    hidden: int
    contacts: list[RecruiterContactRead]
