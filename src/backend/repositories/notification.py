"""Notification repositories."""

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.notification import (
    Notification,
    NotificationCategory,
    NotificationPreference,
    NotificationStatus,
)
from backend.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Notification)

    async def get_for_candidate(
        self, notification_id: UUID, candidate_id: UUID
    ) -> Notification | None:
        stmt = select(Notification).where(
            Notification.id == notification_id,
            Notification.candidate_id == candidate_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_candidate(
        self,
        candidate_id: UUID,
        *,
        status: NotificationStatus | None = None,
        category: NotificationCategory | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Notification]:
        stmt = select(Notification).where(Notification.candidate_id == candidate_id)
        if status is not None:
            stmt = stmt.where(Notification.status == status)
        if category is not None:
            stmt = stmt.where(Notification.category == category)
        stmt = (
            stmt.order_by(Notification.__table__.c.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_for_candidate(
        self,
        candidate_id: UUID,
        *,
        status: NotificationStatus | None = None,
        category: NotificationCategory | None = None,
    ) -> int:
        stmt = (
            select(func.count()).select_from(Notification).where(Notification.candidate_id == candidate_id)
        )
        if status is not None:
            stmt = stmt.where(Notification.status == status)
        if category is not None:
            stmt = stmt.where(Notification.category == category)
        return int((await self.session.execute(stmt)).scalar_one())

    async def has_unread(
        self,
        candidate_id: UUID,
        category: NotificationCategory,
        entity_type: str | None,
        entity_id: str | None,
    ) -> bool:
        stmt = select(Notification.id).where(
            Notification.candidate_id == candidate_id,
            Notification.category == category,
            Notification.status == NotificationStatus.UNREAD,
        )
        if entity_type is not None:
            stmt = stmt.where(Notification.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(Notification.entity_id == entity_id)
        stmt = stmt.limit(1)
        return (await self.session.execute(stmt)).scalar_one_or_none() is not None

    async def mark_all_read(self, candidate_id: UUID) -> int:
        stmt = (
            update(Notification)
            .where(
                Notification.candidate_id == candidate_id,
                Notification.status == NotificationStatus.UNREAD,
            )
            .values(status=NotificationStatus.READ)
        )
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0)


class NotificationPreferenceRepository(BaseRepository[NotificationPreference]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, NotificationPreference)

    async def get_for_candidate(self, candidate_id: UUID) -> NotificationPreference | None:
        stmt = select(NotificationPreference).where(
            NotificationPreference.candidate_id == candidate_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
