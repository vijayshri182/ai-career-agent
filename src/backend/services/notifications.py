"""Notification service (Phase 10).

Emits in-app notifications for pipeline events. Notifications are short-lived,
candidate-scoped alerts; preferences gate delivery per category and channel.
Security alerts always bypass preference muting. Delivery is best-effort and
never raises: an alert must not break the workflow that produced it.
"""

from uuid import UUID

from backend.core.exceptions import NotFoundError
from backend.models.notification import (
    Notification,
    NotificationCategory,
    NotificationChannel,
    NotificationPreference,
    NotificationStatus,
)
from backend.repositories.audit import AuditRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.notification import (
    NotificationPreferenceRepository,
    NotificationRepository,
)
from backend.schemas.notifications import NotificationPreferenceUpdate


class NotificationService:
    def __init__(
        self,
        *,
        candidate_repo: CandidateRepository,
        notification_repo: NotificationRepository,
        preference_repo: NotificationPreferenceRepository,
        audit_repo: AuditRepository,
        actor_id: UUID,
        candidate_id: UUID,
    ) -> None:
        self._candidates = candidate_repo
        self._notifications = notification_repo
        self._preferences = preference_repo
        self._audit = audit_repo
        self._actor_id = actor_id
        self._candidate_id = candidate_id

    # ------------------------------------------------------------- preferences

    async def get_preferences(self) -> NotificationPreference:
        await self._candidates.get_for_user_or_404(self._candidate_id, self._actor_id)
        prefs = await self._preferences.get_for_candidate(self._candidate_id)
        if prefs is None:
            prefs = await self._preferences.create(
                candidate_id=self._candidate_id,
            )
        return prefs

    async def update_preferences(self, payload: NotificationPreferenceUpdate) -> NotificationPreference:
        await self._candidates.get_for_user_or_404(self._candidate_id, self._actor_id)
        prefs = await self._preferences.get_for_candidate(self._candidate_id)
        if prefs is None:
            prefs = await self._preferences.create(
                candidate_id=self._candidate_id,
            )
        changes = payload.model_dump(exclude_unset=True)
        prefs = await self._preferences.update(prefs, **changes)
        await self._audit.log(
            "notifications.preferences_updated",
            actor_id=self._actor_id,
            candidate_id=self._candidate_id,
            entity_type="notification_preferences",
            entity_id=prefs.id,
            metadata={key: bool(value) for key, value in changes.items()},
        )
        return prefs

    # ------------------------------------------------------------ notifications

    async def notify(
        self,
        *,
        category: NotificationCategory,
        title: str,
        detail: str,
        entity_type: str | None = None,
        entity_id: UUID | str | None = None,
        channel: NotificationChannel = NotificationChannel.IN_APP,
    ) -> Notification | None:
        """Create an alert unless muted/deduped. Security alerts bypass muting."""
        try:
            await self._candidates.get_for_user_or_404(self._candidate_id, self._actor_id)
        except NotFoundError:
            return None

        prefs = await self._preferences.get_for_candidate(self._candidate_id)
        if prefs is None:
            prefs = await self._preferences.create(candidate_id=self._candidate_id)

        if category != NotificationCategory.SECURITY_EVENT:
            category_allowed = {
                NotificationCategory.NEW_MATCH: prefs.new_match_enabled,
                NotificationCategory.APPROVAL_NEEDED: prefs.approval_needed_enabled,
                NotificationCategory.APPLICATION_UPDATE: prefs.application_update_enabled,
                NotificationCategory.OUTREACH_RESPONSE: prefs.outreach_response_enabled,
                NotificationCategory.ERROR: prefs.error_enabled,
            }[category]
            channel_allowed = {
                NotificationChannel.IN_APP: prefs.in_app_enabled,
                NotificationChannel.EMAIL: prefs.email_enabled,
                NotificationChannel.SMS: prefs.sms_enabled,
            }[channel]
            if not (category_allowed and channel_allowed):
                return None

        entity_id_str = str(entity_id) if entity_id is not None else None
        if await self._notifications.has_unread(
            self._candidate_id, category, entity_type, entity_id_str
        ):
            return None

        notification = await self._notifications.create(
            candidate_id=self._candidate_id,
            category=category,
            channel=channel,
            status=NotificationStatus.UNREAD,
            title=title,
            detail=detail,
            entity_type=entity_type,
            entity_id=entity_id_str,
        )
        await self._audit.log(
            "notification.created",
            actor_id=self._actor_id,
            candidate_id=self._candidate_id,
            entity_type="notification",
            entity_id=notification.id,
            metadata={"category": category.value, "channel": channel.value},
        )
        return notification

    async def list(
        self,
        *,
        status: NotificationStatus | None = None,
        category: NotificationCategory | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Notification], int]:
        await self._candidates.get_for_user_or_404(self._candidate_id, self._actor_id)
        items = await self._notifications.list_for_candidate(
            self._candidate_id, status=status, category=category, limit=limit, offset=offset
        )
        total = await self._notifications.count_for_candidate(
            self._candidate_id, status=status, category=category
        )
        return items, total

    async def unread_count(self) -> int:
        await self._candidates.get_for_user_or_404(self._candidate_id, self._actor_id)
        return await self._notifications.count_for_candidate(
            self._candidate_id, status=NotificationStatus.UNREAD
        )

    async def mark_read(self, notification_id: UUID) -> Notification:
        await self._candidates.get_for_user_or_404(self._candidate_id, self._actor_id)
        notification = await self._notifications.get_for_candidate(
            notification_id, self._candidate_id
        )
        if notification is None:
            raise NotFoundError("Notification not found")
        if notification.status == NotificationStatus.UNREAD:
            from datetime import UTC, datetime

            notification = await self._notifications.update(
                notification,
                status=NotificationStatus.READ,
                read_at=datetime.now(UTC),
            )
        return notification

    async def mark_all_read(self) -> int:
        await self._candidates.get_for_user_or_404(self._candidate_id, self._actor_id)
        updated = await self._notifications.mark_all_read(self._candidate_id)
        await self._audit.log(
            "notifications.read_all",
            actor_id=self._actor_id,
            candidate_id=self._candidate_id,
            metadata={"updated": updated},
        )
        return updated
