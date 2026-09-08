"""Experience router."""

from uuid import UUID

from fastapi import APIRouter, Depends, status

from backend.api.deps import (
    get_current_user_id,
    get_experience_service,
    handle_domain_error,
)
from backend.schemas.experience import ExperienceCreate, ExperienceRead, ExperienceUpdate
from backend.services.experience import ExperienceService

router = APIRouter(prefix="/candidates/{candidate_id}/experience", tags=["experience"])


@router.get("", response_model=list[ExperienceRead])
async def list_experience(
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ExperienceService = Depends(get_experience_service),
):
    return await service.list(candidate_id)


@router.post("", response_model=ExperienceRead, status_code=status.HTTP_201_CREATED)
async def add_experience(
    candidate_id: UUID,
    data: ExperienceCreate,
    user_id: UUID = Depends(get_current_user_id),
    service: ExperienceService = Depends(get_experience_service),
):
    try:
        exp = await service.add(candidate_id, user_id, data)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return exp


@router.put("/{experience_id}", response_model=ExperienceRead)
async def update_experience(
    candidate_id: UUID,
    experience_id: UUID,
    data: ExperienceUpdate,
    user_id: UUID = Depends(get_current_user_id),
    service: ExperienceService = Depends(get_experience_service),
):
    try:
        exp = await service.update(candidate_id, user_id, experience_id, data)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return exp


@router.delete("/{experience_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_experience(
    candidate_id: UUID,
    experience_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ExperienceService = Depends(get_experience_service),
):
    try:
        await service.delete(candidate_id, user_id, experience_id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return None
