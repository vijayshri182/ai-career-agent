"""Job postings router."""

from uuid import UUID

from fastapi import APIRouter, Depends

from backend.api.deps import (
    get_current_user_id,
    get_job_service,
    get_owned_candidate,
    handle_domain_error,
)
from backend.models.job import JobStatus
from backend.schemas.job import JobRead
from backend.services.job import JobService

router = APIRouter(prefix="/candidates/{candidate_id}/jobs", tags=["jobs"])


@router.get("", response_model=list[JobRead], dependencies=[Depends(get_owned_candidate)])
async def list_jobs(
    candidate_id: UUID,
    status: JobStatus | None = None,
    limit: int = 100,
    offset: int = 0,
    user_id: UUID = Depends(get_current_user_id),
    service: JobService = Depends(get_job_service),
):
    try:
        return await service.list(
            candidate_id, user_id, status=status, limit=limit, offset=offset
        )
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get("/{job_id}", response_model=JobRead, dependencies=[Depends(get_owned_candidate)])
async def get_job(
    candidate_id: UUID,
    job_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: JobService = Depends(get_job_service),
):
    try:
        return await service.get(candidate_id, user_id, job_id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
