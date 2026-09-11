"""Job discovery runs router."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import (
    get_current_user_id,
    get_discovery_service,
    get_owned_candidate,
    get_session,
    handle_domain_error,
)
from backend.repositories.agent_task import AgentTaskRepository
from backend.schemas.agent_task import AgentTaskRead
from backend.schemas.discovery import DiscoveryRunRequest, DiscoveryRunResult
from backend.services.discovery import DiscoveryService

router = APIRouter(prefix="/candidates/{candidate_id}/discovery-runs", tags=["discovery"])


@router.post(
    "",
    response_model=DiscoveryRunResult,
    dependencies=[Depends(get_owned_candidate)],
)
async def run_discovery(
    candidate_id: UUID,
    data: DiscoveryRunRequest | None = None,
    user_id: UUID = Depends(get_current_user_id),
    service: DiscoveryService = Depends(get_discovery_service),
):
    try:
        source_ids = list(data.source_ids) if data else None
        return await service.run_discovery(candidate_id, user_id, source_ids)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get("", response_model=list[AgentTaskRead], dependencies=[Depends(get_owned_candidate)])
async def list_discovery_runs(
    candidate_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    return await AgentTaskRepository(session).list_for_candidate(
        candidate_id, task_type="job_discovery"
    )
