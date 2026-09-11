"""Job sources router."""

from uuid import UUID

from fastapi import APIRouter, Depends, status

from backend.api.deps import (
    get_current_user_id,
    get_job_source_service,
    get_owned_candidate,
    handle_domain_error,
)
from backend.schemas.job_source import JobSourceCreate, JobSourceRead, JobSourceUpdate
from backend.services.job_source import JobSourceService

router = APIRouter(prefix="/candidates/{candidate_id}/job-sources", tags=["job-sources"])


@router.get("", response_model=list[JobSourceRead], dependencies=[Depends(get_owned_candidate)])
async def list_sources(
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: JobSourceService = Depends(get_job_source_service),
):
    return await service.list(candidate_id, user_id)


@router.post(
    "",
    response_model=JobSourceRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_owned_candidate)],
)
async def add_source(
    candidate_id: UUID,
    data: JobSourceCreate,
    user_id: UUID = Depends(get_current_user_id),
    service: JobSourceService = Depends(get_job_source_service),
):
    try:
        return await service.create(candidate_id, user_id, data)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.put(
    "/{source_id}",
    response_model=JobSourceRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def update_source(
    candidate_id: UUID,
    source_id: UUID,
    data: JobSourceUpdate,
    user_id: UUID = Depends(get_current_user_id),
    service: JobSourceService = Depends(get_job_source_service),
):
    try:
        return await service.update(candidate_id, user_id, source_id, data)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.delete(
    "/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_owned_candidate)],
)
async def delete_source(
    candidate_id: UUID,
    source_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: JobSourceService = Depends(get_job_source_service),
):
    try:
        await service.delete(candidate_id, user_id, source_id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return None
