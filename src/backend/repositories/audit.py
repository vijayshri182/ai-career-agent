"""Audit event repository."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.audit import AuditEvent
from backend.repositories.base import BaseRepository


class AuditRepository(BaseRepository[AuditEvent]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AuditEvent)

    async def log(
        self,
        event_type: str,
        actor_id: UUID | None,
        candidate_id: UUID | str | None = None,
        entity_type: str | None = None,
        entity_id: UUID | str | None = None,
        result: str = "success",
        request_id: str | None = None,
        metadata: dict[str, object] | None = None,
        details: str | None = None,
    ) -> AuditEvent:
        def _str(value: UUID | str | None) -> str | None:
            return str(value) if isinstance(value, UUID) else value

        return await self.create(
            event_type=event_type,
            actor_id=_str(actor_id),
            candidate_id=_str(candidate_id),
            entity_type=entity_type,
            entity_id=_str(entity_id),
            result=result,
            request_id=request_id,
            event_metadata=metadata or {},
            details=details,
        )

    async def list_for_candidate(
        self,
        candidate_id: UUID,
        *,
        event_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditEvent]:
        stmt = select(AuditEvent).where(AuditEvent.candidate_id == str(candidate_id))
        if event_type:
            stmt = stmt.where(AuditEvent.event_type == event_type)
        stmt = stmt.order_by(AuditEvent.__table__.c.created_at.desc()).limit(limit).offset(offset)
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_for_candidate(
        self,
        candidate_id: UUID,
        *,
        event_type: str | None = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.candidate_id == str(candidate_id))
        )
        if event_type:
            stmt = stmt.where(AuditEvent.event_type == event_type)
        return int((await self.session.execute(stmt)).scalar_one())
