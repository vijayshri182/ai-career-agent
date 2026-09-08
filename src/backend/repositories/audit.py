"""Audit event repository."""

from uuid import UUID

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
