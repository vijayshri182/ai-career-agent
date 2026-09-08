"""Education router."""

from uuid import UUID

from fastapi import APIRouter, Depends, status

from backend.api.deps import (
    get_current_user_id,
    get_education_service,
    handle_domain_error,
)
from backend.schemas.education import EducationCreate, EducationRead, EducationUpdate
from backend.services.education import EducationService

router = APIRouter(prefix="/candidates/{candidate_id}/education", tags=["education"])


@router.get("", response_model=list[EducationRead])
async def list_education(
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: EducationService = Depends(get_education_service),
):
    return await service.list(candidate_id)


@router.post("", response_model=EducationRead, status_code=status.HTTP_201_CREATED)
async def add_education(
    candidate_id: UUID,
    data: EducationCreate,
    user_id: UUID = Depends(get_current_user_id),
    service: EducationService = Depends(get_education_service),
):
    try:
        edu = await service.add(candidate_id, user_id, data)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return edu


@router.put("/{education_id}", response_model=EducationRead)
async def update_education(
    candidate_id: UUID,
    education_id: UUID,
    data: EducationUpdate,
    user_id: UUID = Depends(get_current_user_id),
    service: EducationService = Depends(get_education_service),
):
    try:
        edu = await service.update(candidate_id, user_id, education_id, data)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return edu


@router.delete("/{education_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_education(
    candidate_id: UUID,
    education_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: EducationService = Depends(get_education_service),
):
    try:
        await service.delete(candidate_id, user_id, education_id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return None
