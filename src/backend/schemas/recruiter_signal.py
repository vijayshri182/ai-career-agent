"""Recruiter signal schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.models.recruiter_signal import (
    RecruiterSignalStatus,
    RecruiterSignalType,
)


class RecruiterSignalCreate(BaseModel):
    """Input for recording an evidence-backed recruiter signal (no generation)."""

    job_id: UUID
    recruiter_contact_id: UUID | None = Field(default=None)
    company_id: UUID | None = Field(default=None)
    signal_type: RecruiterSignalType
    source: str = Field(min_length=1, max_length=128)
    source_reference: str | None = Field(default=None, max_length=255)
    evidence: dict[str, Any] | None = Field(default=None)
    provenance: dict[str, Any] | None = Field(default=None)


class RecruiterSignalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    job_id: UUID
    recruiter_contact_id: UUID | None
    company_id: UUID | None
    signal_type: RecruiterSignalType
    status: RecruiterSignalStatus
    signal_identity: str
    source: str
    source_reference: str | None
    evidence_json: dict[str, Any]
    provenance_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class RecruiterSignalStatusUpdate(BaseModel):
    """Explicit status transition (never applied implicitly)."""

    status: RecruiterSignalStatus


class RecruiterSignalListResponse(BaseModel):
    items: list[RecruiterSignalRead]
    total: int
