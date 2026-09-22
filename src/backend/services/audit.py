"""Audit trail read service."""

from __future__ import annotations

from uuid import UUID

from backend.models.audit import AuditEvent
from backend.repositories.audit import AuditRepository
from backend.repositories.candidate import CandidateRepository


class AuditTrailService:
    """Candidate-scoped, read-only access to the append-only audit log."""

    def __init__(
        self,
        *,
        candidate_id: UUID,
        actor_id: UUID,
        candidate_repo: CandidateRepository,
        audit_repo: AuditRepository,
    ) -> None:
        self._candidate_id = candidate_id
        self._actor_id = actor_id
        self._candidates = candidate_repo
        self._audit = audit_repo

    async def _ensure_owned_candidate(self) -> None:
        await self._candidates.get_for_user_or_404(self._candidate_id, self._actor_id)

    async def list_events(
        self,
        *,
        event_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[AuditEvent], int]:
        await self._ensure_owned_candidate()
        items = await self._audit.list_for_candidate(
            self._candidate_id, event_type=event_type, limit=limit, offset=offset
        )
        total = await self._audit.count_for_candidate(
            self._candidate_id, event_type=event_type
        )
        return items, total
