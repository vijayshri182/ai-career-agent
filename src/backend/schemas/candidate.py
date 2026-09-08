"""Candidate profile schemas."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.models.candidate import ProfileStatus, WorkMode


class Compensation(BaseModel):
    amount: int | None = None
    currency: str | None = None


class CandidateCreate(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    headline: str | None = None
    summary: str | None = None
    current_role: str | None = None
    target_role: str | None = None
    total_experience_years: int | None = None
    current_location: dict[str, object] | None = None
    work_authorization: str | None = None
    work_mode_preference: WorkMode | None = None
    notice_period_days: int | None = None
    expected_compensation_amount: int | None = None
    expected_compensation_currency: str | None = None
    employment_type: str | None = None
    seniority: str | None = None


class CandidateUpdate(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    headline: str | None = None
    summary: str | None = None
    current_role: str | None = None
    target_role: str | None = None
    total_experience_years: int | None = None
    current_location: dict[str, object] | None = None
    work_authorization: str | None = None
    work_mode_preference: WorkMode | None = None
    notice_period_days: int | None = None
    expected_compensation_amount: int | None = None
    expected_compensation_currency: str | None = None
    employment_type: str | None = None
    seniority: str | None = None
    status: ProfileStatus | None = None


class CandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    full_name: str | None
    email: str | None
    phone: str | None
    headline: str | None
    summary: str | None
    current_role: str | None
    target_role: str | None
    total_experience_years: int | None
    current_location: dict[str, object] | None
    work_authorization: str | None
    work_mode_preference: WorkMode | None
    notice_period_days: int | None
    expected_compensation_amount: int | None
    expected_compensation_currency: str | None
    employment_type: str | None
    seniority: str | None
    career_preferences: dict[str, object]
    status: ProfileStatus
