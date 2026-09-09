"""Skills router."""

from uuid import UUID

from fastapi import APIRouter, Depends, status

from backend.api.deps import (
    get_current_user_id,
    get_owned_candidate,
    get_skill_service,
    handle_domain_error,
)
from backend.schemas.skill import SkillCreate, SkillRead, SkillUpdate
from backend.services.skill import SkillService

router = APIRouter(prefix="/candidates/{candidate_id}/skills", tags=["skills"])


@router.get("", response_model=list[SkillRead], dependencies=[Depends(get_owned_candidate)])
async def list_skills(
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: SkillService = Depends(get_skill_service),
):
    return await service.list(candidate_id, user_id)


@router.post(
    "",
    response_model=SkillRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_owned_candidate)],
)
async def add_skill(
    candidate_id: UUID,
    data: SkillCreate,
    user_id: UUID = Depends(get_current_user_id),
    service: SkillService = Depends(get_skill_service),
):
    try:
        skill = await service.add(candidate_id, user_id, data)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return skill


@router.put(
    "/{skill_id}",
    response_model=SkillRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def update_skill(
    candidate_id: UUID,
    skill_id: UUID,
    data: SkillUpdate,
    user_id: UUID = Depends(get_current_user_id),
    service: SkillService = Depends(get_skill_service),
):
    try:
        skill = await service.update(candidate_id, user_id, skill_id, data)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return skill


@router.delete(
    "/{skill_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_owned_candidate)],
)
async def delete_skill(
    candidate_id: UUID,
    skill_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: SkillService = Depends(get_skill_service),
):
    try:
        await service.delete(candidate_id, user_id, skill_id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return None
