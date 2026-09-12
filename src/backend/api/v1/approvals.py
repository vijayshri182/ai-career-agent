"""Human approval workflow router.

External actions (application submission, outreach send) are gated behind an
explicit approval. Everything is candidate-scoped; ownership is enforced at the
HTTP layer via ``get_owned_candidate`` and re-checked in the service.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from backend.api.deps import (
    get_application_prep_service,
    get_approval_service,
    get_current_user_id,
    get_owned_candidate,
    handle_domain_error,
)
from backend.models.approval import ApprovalDecisionType, ApprovalKind, ApprovalStatus
from backend.schemas.approval import (
    ApprovalDecisionRead,
    ApprovalDetailRead,
    ApprovalListResponse,
    ApprovalRead,
    ApprovalRequestResponse,
    ApprovalSnoozeRequest,
)
from backend.services.application_prep import ApplicationPrepService
from backend.services.approval import ApprovalService

router = APIRouter(prefix="/candidates/{candidate_id}", tags=["approvals"])


def _approval_read(a: object) -> ApprovalRead:
    return ApprovalRead.model_validate(a)


def _approval_detail_read(a: object) -> ApprovalDetailRead:
    return ApprovalDetailRead.model_validate(a)


def _decision_read(d: object) -> ApprovalDecisionRead:
    return ApprovalDecisionRead.model_validate(d)


@router.get(
    "/approvals",
    response_model=ApprovalListResponse,
    dependencies=[Depends(get_owned_candidate)],
)
async def list_approvals(
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ApprovalService = Depends(get_approval_service),
    status: ApprovalStatus | None = Query(default=None),
    kind: ApprovalKind | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    try:
        items, total = await service.list_approvals(
            status=status, kind=kind, limit=limit, offset=offset
        )
        return ApprovalListResponse(items=[_approval_read(a) for a in items], total=total)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get(
    "/approvals/{approval_id}",
    response_model=ApprovalDetailRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def get_approval(
    candidate_id: UUID,
    approval_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ApprovalService = Depends(get_approval_service),
):
    try:
        return _approval_detail_read(await service.get_approval(approval_id, with_decisions=True))
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post(
    "/approvals/{approval_id}/approve",
    response_model=ApprovalRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def approve_approval(
    candidate_id: UUID,
    approval_id: UUID,
    note: str | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
    service: ApprovalService = Depends(get_approval_service),
):
    try:
        return _approval_read(
            await service.decide(approval_id, ApprovalDecisionType.APPROVE, note=note)
        )
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post(
    "/approvals/{approval_id}/reject",
    response_model=ApprovalRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def reject_approval(
    candidate_id: UUID,
    approval_id: UUID,
    note: str | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
    service: ApprovalService = Depends(get_approval_service),
):
    try:
        return _approval_read(
            await service.decide(approval_id, ApprovalDecisionType.REJECT, note=note)
        )
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post(
    "/approvals/{approval_id}/snooze",
    response_model=ApprovalRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def snooze_approval(
    candidate_id: UUID,
    approval_id: UUID,
    request: ApprovalSnoozeRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: ApprovalService = Depends(get_approval_service),
):
    try:
        return _approval_read(
            await service.decide(
                approval_id,
                ApprovalDecisionType.SNOOZE,
                note=request.note,
                snoozed_until=request.until,
            )
        )
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post(
    "/approvals/{approval_id}/cancel",
    response_model=ApprovalRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def cancel_approval(
    candidate_id: UUID,
    approval_id: UUID,
    note: str | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
    service: ApprovalService = Depends(get_approval_service),
):
    try:
        return _approval_read(
            await service.decide(approval_id, ApprovalDecisionType.CANCEL, note=note)
        )
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post(
    "/applications/{application_id}/approval-request",
    response_model=ApprovalRequestResponse,
    dependencies=[Depends(get_owned_candidate)],
)
async def request_application_approval(
    candidate_id: UUID,
    application_id: UUID,
    summary: str | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
    service: ApprovalService = Depends(get_approval_service),
    prep: ApplicationPrepService = Depends(get_application_prep_service),
):
    try:
        detail = await prep.get_application_detail(candidate_id, user_id, application_id)
        context: dict[str, object] = {
            "match_score": detail.match_score,
            "application_status": detail.status.value,
            "documents": [d.doc_type.value for d in detail.documents],
        }
        approval = await service.request_approval(
            kind=ApprovalKind.APPLICATION_SUBMISSION,
            target_type="application",
            target_id=application_id,
            summary=summary or "Submit the prepared application",
            context=context,
            application_id=application_id,
        )
        return ApprovalRequestResponse(approval=_approval_read(approval))
    except Exception as exc:
        raise handle_domain_error(exc) from exc
