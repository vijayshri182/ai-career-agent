"""Dashboard summary service (Phase 10).

Composes the analytics read-model with recommendation and notification counts
plus the most recent audit events into a single observability view. Reuses
`AnalyticsService.summary()` so there is exactly one aggregation implementation.
"""

from datetime import UTC, datetime
from uuid import UUID

from backend.models.learning import RecommendationStatus
from backend.repositories.audit import AuditRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.learning import RecommendationRepository
from backend.schemas.dashboard import DashboardSummary, RecentAuditEntry
from backend.services.analytics import AnalyticsService
from backend.services.notifications import NotificationService


class DashboardService:
    def __init__(
        self,
        *,
        candidate_repo: CandidateRepository,
        analytics: AnalyticsService,
        notifications: NotificationService,
        recommendation_repo: RecommendationRepository,
        audit_repo: AuditRepository,
        actor_id: UUID,
        candidate_id: UUID,
    ) -> None:
        self._candidates = candidate_repo
        self._analytics = analytics
        self._notifications = notifications
        self._recommendations = recommendation_repo
        self._audit = audit_repo
        self._actor_id = actor_id
        self._candidate_id = candidate_id

    async def summary(self) -> DashboardSummary:
        await self._candidates.get_for_user_or_404(self._candidate_id, self._actor_id)
        analytics = await self._analytics.summary()
        unread = await self._notifications.unread_count()
        active = await self._recommendations.count_for_candidate(
            self._candidate_id, status=RecommendationStatus.ACTIVE
        )
        total = await self._recommendations.count_for_candidate(self._candidate_id)
        events = await self._audit.list_for_candidate(self._candidate_id, limit=5)
        return DashboardSummary(
            applications=analytics.applications,
            matches=analytics.matches,
            outreach=analytics.outreach,
            feedback=analytics.feedback,
            profile=analytics.profile,
            recommendations_active=active,
            recommendations_total=total,
            notifications_unread=unread,
            recent_activity=[
                RecentAuditEntry(
                    event_type=event.event_type,
                    entity_type=event.entity_type,
                    entity_id=str(event.entity_id) if event.entity_id else None,
                    result=event.result,
                    created_at=event.created_at,
                )
                for event in events
            ],
            generated_at=datetime.now(UTC),
        )
