"""Outreach repositories."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models.outreach import (
    OutreachChannel,
    OutreachMessage,
    OutreachMessageVersion,
    OutreachRun,
    OutreachRunStatus,
    OutreachStatus,
    ResponseStatus,
)
from backend.repositories.base import BaseRepository

OPEN_RUN_STATUSES = (OutreachRunStatus.PENDING, OutreachRunStatus.RUNNING)


class OutreachMessageRepository(BaseRepository[OutreachMessage]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, OutreachMessage)

    async def get_for_candidate(
        self, message_id: UUID, candidate_id: UUID
    ) -> OutreachMessage | None:
        stmt = select(OutreachMessage).where(
            OutreachMessage.id == message_id,
            OutreachMessage.candidate_id == candidate_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_for_candidate_detailed(
        self, message_id: UUID, candidate_id: UUID
    ) -> OutreachMessage | None:
        stmt = (
            select(OutreachMessage)
            .where(
                OutreachMessage.id == message_id,
                OutreachMessage.candidate_id == candidate_id,
            )
            .options(
                selectinload(OutreachMessage.versions),
                selectinload(OutreachMessage.runs),
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_candidate(
        self,
        candidate_id: UUID,
        *,
        contact_id: UUID | None = None,
        job_id: UUID | None = None,
        status: OutreachStatus | None = None,
        channel: OutreachChannel | None = None,
        is_follow_up: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[OutreachMessage]:
        stmt = select(OutreachMessage).where(OutreachMessage.candidate_id == candidate_id)
        if contact_id is not None:
            stmt = stmt.where(OutreachMessage.contact_id == contact_id)
        if job_id is not None:
            stmt = stmt.where(OutreachMessage.job_id == job_id)
        if status is not None:
            stmt = stmt.where(OutreachMessage.status == status)
        if channel is not None:
            stmt = stmt.where(OutreachMessage.channel == channel)
        if is_follow_up is not None:
            stmt = stmt.where(OutreachMessage.is_follow_up.is_(is_follow_up))
        stmt = (
            stmt.order_by(OutreachMessage.__table__.c.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_for_candidate(
        self,
        candidate_id: UUID,
        *,
        status: OutreachStatus | None = None,
        channel: OutreachChannel | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(OutreachMessage).where(
            OutreachMessage.candidate_id == candidate_id
        )
        if status is not None:
            stmt = stmt.where(OutreachMessage.status == status)
        if channel is not None:
            stmt = stmt.where(OutreachMessage.channel == channel)
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_sent_since(self, candidate_id: UUID, since: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(OutreachMessage)
            .where(
                OutreachMessage.candidate_id == candidate_id,
                OutreachMessage.status == OutreachStatus.SENT,
                OutreachMessage.sent_at >= since,
            )
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_responded(self, candidate_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(OutreachMessage)
            .where(
                OutreachMessage.candidate_id == candidate_id,
                OutreachMessage.response_status == ResponseStatus.RESPONDED,
            )
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_by_status(self, candidate_id: UUID) -> dict[OutreachStatus, int]:
        stmt = (
            select(OutreachMessage.status, func.count())
            .where(OutreachMessage.candidate_id == candidate_id)
            .group_by(OutreachMessage.status)
        )
        result = await self.session.execute(stmt)
        return {status: int(count) for status, count in result.all()}


class OutreachMessageVersionRepository(BaseRepository[OutreachMessageVersion]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, OutreachMessageVersion)

    async def next_version_number(self, message_id: UUID) -> int:
        stmt = select(func.max(OutreachMessageVersion.version_number)).where(
            OutreachMessageVersion.message_id == message_id
        )
        current = (await self.session.execute(stmt)).scalar_one()
        return int(current or 0) + 1

    async def list_for_message(self, message_id: UUID) -> list[OutreachMessageVersion]:
        stmt = (
            select(OutreachMessageVersion)
            .where(OutreachMessageVersion.message_id == message_id)
            .order_by(OutreachMessageVersion.version_number.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())


class OutreachRunRepository(BaseRepository[OutreachRun]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, OutreachRun)

    async def get_for_candidate(self, run_id: UUID, candidate_id: UUID) -> OutreachRun | None:
        stmt = select(OutreachRun).where(
            OutreachRun.id == run_id,
            OutreachRun.candidate_id == candidate_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_for_message(self, message_id: UUID) -> OutreachRun | None:
        stmt = (
            select(OutreachRun)
            .where(OutreachRun.message_id == message_id)
            .order_by(OutreachRun.__table__.c.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def get_active_for_message(self, message_id: UUID) -> OutreachRun | None:
        stmt = (
            select(OutreachRun)
            .where(OutreachRun.message_id == message_id)
            .where(OutreachRun.status.in_(OPEN_RUN_STATUSES))
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def list_for_candidate(
        self,
        candidate_id: UUID,
        *,
        status: OutreachRunStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[OutreachRun]:
        stmt = select(OutreachRun).where(OutreachRun.candidate_id == candidate_id)
        if status is not None:
            stmt = stmt.where(OutreachRun.status == status)
        stmt = (
            stmt.order_by(OutreachRun.__table__.c.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_for_candidate(
        self, candidate_id: UUID, status: OutreachRunStatus | None = None
    ) -> int:
        stmt = select(func.count()).select_from(OutreachRun).where(
            OutreachRun.candidate_id == candidate_id
        )
        if status is not None:
            stmt = stmt.where(OutreachRun.status == status)
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_by_status(self, candidate_id: UUID) -> dict[OutreachRunStatus, int]:
        stmt = (
            select(OutreachRun.status, func.count())
            .where(OutreachRun.candidate_id == candidate_id)
            .group_by(OutreachRun.status)
        )
        result = await self.session.execute(stmt)
        return {status: int(count) for status, count in result.all()}
