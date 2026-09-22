"""Dashboard summary router."""

from uuid import UUID

from fastapi import APIRouter, Depends

from backend.api.deps import get_dashboard_service, handle_domain_error
from backend.core.exceptions import NotFoundError, ValidationError
from backend.schemas.dashboard import DashboardSummary
from backend.services.dashboard import DashboardService

router = APIRouter(prefix="/candidates/{candidate_id}", tags=["dashboard"])


@router.get("/dashboard/summary", response_model=DashboardSummary)
async def dashboard_summary(
    candidate_id: UUID,
    service: DashboardService = Depends(get_dashboard_service),
) -> DashboardSummary:
    try:
        return await service.summary()
    except (NotFoundError, ValidationError) as exc:
        raise handle_domain_error(exc) from exc
