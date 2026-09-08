"""Resume schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.models.resume import ResumeStatus, ResumeType


class ResumeCreate(BaseModel):
    name: str
    resume_type: ResumeType = ResumeType.GENERAL
    target_role: str | None = None
    is_default: bool = False


class ResumeUpdate(BaseModel):
    name: str | None = None
    resume_type: ResumeType | None = None
    target_role: str | None = None
    is_default: bool | None = None
    status: ResumeStatus | None = None


class ResumeVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    resume_id: UUID
    version_number: int
    original_filename: str
    content_type: str
    size_bytes: int
    parsed_status: str
    parsed_at: datetime | None
    created_at: datetime


class ResumeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    name: str
    resume_type: ResumeType
    target_role: str | None
    is_default: bool
    status: ResumeStatus
    active_version_id: UUID | None
    active_version: ResumeVersionRead | None
    created_at: datetime
    updated_at: datetime


class ParsedResumeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    resume_version_id: UUID
    extracted_data: dict[str, object]
    status: str
    confidence_score: int | None
    created_at: datetime


class ApplyParsedResumeRequest(BaseModel):
    confirm: bool = True
