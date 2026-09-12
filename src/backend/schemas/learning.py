"""Learning / optimization schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.models.learning import (
    FeedbackOutcome,
    RecommendationKind,
    RecommendationStatus,
)


class FeedbackCreate(BaseModel):
    outcome: FeedbackOutcome
    application_id: UUID | None = None
    outreach_message_id: UUID | None = None
    stage: str | None = Field(default=None, max_length=128)
    note: str | None = Field(default=None, max_length=2000)


class FeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    application_id: UUID | None
    outreach_message_id: UUID | None
    outcome: FeedbackOutcome
    stage: str | None
    note: str | None
    happened_at: datetime
    created_at: datetime


class FeedbackListResponse(BaseModel):
    items: list[FeedbackRead]
    total: int


class RecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    kind: RecommendationKind
    source_key: str
    title: str
    detail: str
    rationale: list[str]
    status: RecommendationStatus
    created_at: datetime
    updated_at: datetime


class RecommendationListResponse(BaseModel):
    items: list[RecommendationRead]
    total: int


class ApplicationFunnel(BaseModel):
    total: int
    draft: int
    ready: int
    submitted: int
    withdrawn: int


class MatchAnalytics(BaseModel):
    total: int
    matched: int
    rejected: int
    pending: int
    avg_score: float | None
    avg_confidence: float | None
    top_missing_skills: list[str]


class OutreachAnalytics(BaseModel):
    sent: int
    responded: int
    response_rate: float | None


class FeedbackAnalytics(BaseModel):
    total: int
    by_outcome: dict[str, int]


class ProfileMetrics(BaseModel):
    skills_count: int
    experiences_count: int
    educations_count: int
    certifications_count: int
    jobs_count: int


class AnalyticsSummary(BaseModel):
    applications: ApplicationFunnel
    matches: MatchAnalytics
    outreach: OutreachAnalytics
    feedback: FeedbackAnalytics
    profile: ProfileMetrics
    generated_at: datetime
