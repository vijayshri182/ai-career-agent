"""Candidate-scoped audit trail router.

Read-only access to the append-only audit log. Ownership is enforced at the
HTTP layer via ``get_owned_candidate`` and re-checked in the service.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from backend.api.deps import get_audit_trail_service, get_owned_candidate
from backend.schemas.audit import AuditEventListResponse, AuditEventRead
from backend.services.audit import AuditTrailService

router = APIRouter(prefix="/candidates/{candidate_id}", tags=["audit"])


@router.get(
    "/audit-events",
    response_model=AuditEventListResponse,
    dependencies=[Depends(get_owned_candidate)],
)
async def list_audit_events(
    candidate_id: UUID,  # noqa: ARG001
    service: AuditTrailService = Depends(get_audit_trail_service),
    event_type: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AuditEventListResponse:
    items, total = await service.list_events(
        event_type=event_type, limit=limit, offset=offset
    )
    return AuditEventListResponse(
        items=[AuditEventRead.model_validate(item) for item in items], total=total
    )
