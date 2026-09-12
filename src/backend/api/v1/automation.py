"""Permitted application automation router.

Candidate-scoped (project convention): every route depends on
``get_owned_candidate`` (404 for cross-user/non-existent candidates) and the
service re-checks ownership as defense-in-depth. Execution is gated by an
APPROVED approval and a source that explicitly permits automation; challenges
pause the run and hand off to the human-in-the-loop machinery.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from backend.api.deps import (
    get_application_automation_service,
    get_current_user_id,
    get_owned_candidate,
    handle_domain_error,
)
from backend.models.automation_run import AutomationRun, AutomationRunStatus
from backend.schemas.automation import (
    AutomationRunListResponse,
    AutomationRunRead,
    AutomationStatusSummary,
)
from backend.services.application_automation import ApplicationAutomationService

router = APIRouter(prefix="/candidates/{candidate_id}", tags=["automation"])


def _run_read(run: AutomationRun) -> AutomationRunRead:
    return AutomationRunRead.model_validate(run)


@router.post(
    "/applications/{application_id}/execute",
    response_model=AutomationRunRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def execute_application(
    candidate_id: UUID,
    application_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ApplicationAutomationService = Depends(get_application_automation_service),
):
    try:
        return _run_read(await service.execute(application_id))
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get(
    "/automation/runs",
    response_model=AutomationRunListResponse,
    dependencies=[Depends(get_owned_candidate)],
)
async def list_runs(
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ApplicationAutomationService = Depends(get_application_automation_service),
    status: AutomationRunStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    try:
        items, total = await service.list_runs(status=status, limit=limit, offset=offset)
        return AutomationRunListResponse(items=[_run_read(r) for r in items], total=total)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get(
    "/automation/runs/{run_id}",
    response_model=AutomationRunRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def get_run(
    candidate_id: UUID,
    run_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ApplicationAutomationService = Depends(get_application_automation_service),
):
    try:
        return _run_read(await service.get_run(run_id))
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post(
    "/automation/runs/{run_id}/retry",
    response_model=AutomationRunRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def retry_run(
    candidate_id: UUID,
    run_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ApplicationAutomationService = Depends(get_application_automation_service),
):
    try:
        return _run_read(await service.retry(run_id))
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get(
    "/automation/status",
    response_model=AutomationStatusSummary,
    dependencies=[Depends(get_owned_candidate)],
)
async def automation_status(
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ApplicationAutomationService = Depends(get_application_automation_service),
):
    try:
        return AutomationStatusSummary(**await service.summary())
    except Exception as exc:
        raise handle_domain_error(exc) from exc
