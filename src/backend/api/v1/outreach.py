"""Outreach router.

Candidate-scoped (project convention): routes depend on ``get_owned_candidate``
and the service re-checks ownership. Sending is human-approval gated and only
ever targets VERIFIED, unsuppressed contacts with a verified destination,
bounded by the daily cap.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from backend.api.deps import (
    get_current_user_id,
    get_outreach_service,
    get_owned_candidate,
    handle_domain_error,
)
from backend.models.outreach import (
    OutreachChannel,
    OutreachRun,
    OutreachRunStatus,
    OutreachStatus,
)
from backend.schemas.outreach import (
    OutreachFollowUpCreate,
    OutreachMessageCreate,
    OutreachMessageDetail,
    OutreachMessageListResponse,
    OutreachMessageRead,
    OutreachMessageUpdate,
    OutreachRespondRequest,
    OutreachRunListResponse,
    OutreachRunRead,
    OutreachStatusSummary,
    OutreachSubmitRequest,
    OutreachSubmitResponse,
    OutreachSuppressRequest,
)
from backend.services.outreach import OutreachService

router = APIRouter(prefix="/candidates/{candidate_id}/outreach", tags=["outreach"])


def _message_read(message) -> OutreachMessageRead:
    return OutreachMessageRead.model_validate(message)


def _run_read(run: OutreachRun) -> OutreachRunRead:
    return OutreachRunRead.model_validate(run)


async def _detail_read(message) -> OutreachMessageDetail:
    detail = OutreachMessageDetail.model_validate(message)
    versions = sorted(message.versions, key=lambda v: v.version_number)
    detail.versions = list(versions)
    detail.runs = sorted(message.runs, key=lambda r: r.created_at)
    return detail


@router.post(
    "/drafts",
    response_model=OutreachMessageRead,
    status_code=201,
    dependencies=[Depends(get_owned_candidate)],
)
async def create_draft(
    candidate_id: UUID,
    payload: OutreachMessageCreate,
    user_id: UUID = Depends(get_current_user_id),
    service: OutreachService = Depends(get_outreach_service),
):
    try:
        message = await service.create_draft(
            contact_id=payload.contact_id,
            job_id=payload.job_id,
            application_id=payload.application_id,
            channel=payload.channel,
            subject=payload.subject,
            body=payload.body,
        )
        return _message_read(message)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post(
    "/follow-ups",
    response_model=OutreachMessageRead,
    status_code=201,
    dependencies=[Depends(get_owned_candidate)],
)
async def create_follow_up(
    candidate_id: UUID,
    payload: OutreachFollowUpCreate,
    user_id: UUID = Depends(get_current_user_id),
    service: OutreachService = Depends(get_outreach_service),
):
    try:
        message = await service.create_follow_up(
            parent_message_id=payload.parent_message_id,
            subject=payload.subject,
            body=payload.body,
        )
        return _message_read(message)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get(
    "/messages",
    response_model=OutreachMessageListResponse,
    dependencies=[Depends(get_owned_candidate)],
)
async def list_messages(
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: OutreachService = Depends(get_outreach_service),
    contact_id: UUID | None = Query(default=None),
    job_id: UUID | None = Query(default=None),
    status: OutreachStatus | None = Query(default=None),
    channel: OutreachChannel | None = Query(default=None),
    is_follow_up: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    try:
        items, total = await service.list_messages(
            contact_id=contact_id,
            job_id=job_id,
            status=status,
            channel=channel,
            is_follow_up=is_follow_up,
            limit=limit,
            offset=offset,
        )
        return OutreachMessageListResponse(
            items=[_message_read(m) for m in items], total=total
        )
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get(
    "/messages/{message_id}",
    response_model=OutreachMessageRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def get_message(
    candidate_id: UUID,
    message_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: OutreachService = Depends(get_outreach_service),
):
    try:
        return _message_read(await service.get_message(message_id))
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get(
    "/messages/{message_id}/detail",
    response_model=OutreachMessageDetail,
    dependencies=[Depends(get_owned_candidate)],
)
async def get_message_detail(
    candidate_id: UUID,
    message_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: OutreachService = Depends(get_outreach_service),
):
    try:
        return await _detail_read(await service.get_message_detail(message_id))
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.put(
    "/messages/{message_id}",
    response_model=OutreachMessageRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def update_draft(
    candidate_id: UUID,
    message_id: UUID,
    payload: OutreachMessageUpdate,
    user_id: UUID = Depends(get_current_user_id),
    service: OutreachService = Depends(get_outreach_service),
):
    try:
        message = await service.update_draft(
            message_id,
            subject=payload.subject,
            body=payload.body,
            change_reason=payload.change_reason,
        )
        return _message_read(message)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post(
    "/messages/{message_id}/submit",
    response_model=OutreachSubmitResponse,
    dependencies=[Depends(get_owned_candidate)],
)
async def submit_for_approval(
    candidate_id: UUID,
    message_id: UUID,
    payload: OutreachSubmitRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: OutreachService = Depends(get_outreach_service),
):
    try:
        approval = await service.submit_for_approval(
            message_id, summary=payload.summary
        )
        message = await service.get_message(message_id)
        return OutreachSubmitResponse(
            message_id=message.id,
            status=message.status,
            approval_id=str(approval.id) if approval else None,
            approval_required=approval is not None,
        )
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post(
    "/messages/{message_id}/cancel",
    response_model=OutreachMessageRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def cancel_message(
    candidate_id: UUID,
    message_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: OutreachService = Depends(get_outreach_service),
):
    try:
        return _message_read(await service.cancel(message_id))
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post(
    "/messages/{message_id}/send",
    response_model=OutreachRunRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def send_message(
    candidate_id: UUID,
    message_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: OutreachService = Depends(get_outreach_service),
):
    try:
        return _run_read(await service.send(message_id))
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post(
    "/messages/{message_id}/respond",
    response_model=OutreachMessageRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def record_response(
    candidate_id: UUID,
    message_id: UUID,
    payload: OutreachRespondRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: OutreachService = Depends(get_outreach_service),
):
    try:
        return _message_read(
            await service.record_response(message_id, note=payload.note)
        )
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post(
    "/messages/{message_id}/suppress",
    response_model=OutreachMessageRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def suppress_message(
    candidate_id: UUID,
    message_id: UUID,
    payload: OutreachSuppressRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: OutreachService = Depends(get_outreach_service),
):
    try:
        return _message_read(await service.mark_suppressed(message_id, reason=payload.reason))
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get(
    "/runs",
    response_model=OutreachRunListResponse,
    dependencies=[Depends(get_owned_candidate)],
)
async def list_runs(
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: OutreachService = Depends(get_outreach_service),
    status: OutreachRunStatus | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    try:
        items, total = await service.list_runs(status=status, limit=limit, offset=offset)
        return OutreachRunListResponse(items=[_run_read(r) for r in items], total=total)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get(
    "/runs/{run_id}",
    response_model=OutreachRunRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def get_run(
    candidate_id: UUID,
    run_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: OutreachService = Depends(get_outreach_service),
):
    try:
        return _run_read(await service.get_run(run_id))
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post(
    "/runs/{run_id}/retry",
    response_model=OutreachRunRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def retry_run(
    candidate_id: UUID,
    run_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: OutreachService = Depends(get_outreach_service),
):
    try:
        return _run_read(await service.retry(run_id))
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get(
    "/status",
    response_model=OutreachStatusSummary,
    dependencies=[Depends(get_owned_candidate)],
)
async def status_summary(
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: OutreachService = Depends(get_outreach_service),
):
    try:
        return OutreachStatusSummary.model_validate(await service.summary())
    except Exception as exc:
        raise handle_domain_error(exc) from exc
