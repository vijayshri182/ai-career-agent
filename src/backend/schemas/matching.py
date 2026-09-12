"""Job matching schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.models.job_match import JobMatchStatus


class JobMatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    job_id: UUID
    status: JobMatchStatus
    score: float
    confidence: float
    is_match: bool
    matched_skills: list[str]
    missing_skills: list[str]
    transferable_skills: list[str]
    strengths: list[str]
    gaps: list[str]
    blockers: list[str]
    recommendation_reasons: list[str]
    rejection_reasons: list[str]
    score_breakdown: dict[str, object]
    rules_version: str
    evaluated_at: datetime
    created_at: datetime
    updated_at: datetime


class BatchMatchResult(BaseModel):
    candidate_id: UUID
    evaluated: int
    updated: int
    errors: int = 0
    matched: int = 0
    rejected: int = 0
    error_metadata: dict[str, str] = {}


class MatchListResponse(BaseModel):
    items: list[JobMatchRead]
    total: int
    limit: int
    offset: int
