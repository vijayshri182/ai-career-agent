"""Dashboard summary schemas."""

from datetime import datetime

from pydantic import BaseModel

from backend.schemas.learning import (
    ApplicationFunnel,
    FeedbackAnalytics,
    MatchAnalytics,
    OutreachAnalytics,
    ProfileMetrics,
)


class RecentAuditEntry(BaseModel):
    event_type: str
    entity_type: str | None
    entity_id: str | None
    result: str
    created_at: datetime


class DashboardSummary(BaseModel):
    applications: ApplicationFunnel
    matches: MatchAnalytics
    outreach: OutreachAnalytics
    feedback: FeedbackAnalytics
    profile: ProfileMetrics
    recommendations_active: int
    recommendations_total: int
    notifications_unread: int
    recent_activity: list[RecentAuditEntry]
    generated_at: datetime
