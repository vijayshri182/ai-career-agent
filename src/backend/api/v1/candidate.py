"""Candidate profile router."""

from uuid import UUID

from fastapi import APIRouter, Depends, status

from backend.api.deps import (
    get_candidate_service,
    get_current_user_id,
    get_profile_service,
    handle_domain_error,
)
from backend.schemas.candidate import CandidateCreate, CandidateRead, CandidateUpdate
from backend.schemas.preferences import CareerPreferences
from backend.schemas.profile import ProfileRead
from backend.services.candidate import CandidateService
from backend.services.profile import ProfileService

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.post("", response_model=CandidateRead, status_code=status.HTTP_201_CREATED)
async def create_candidate(
    data: CandidateCreate,
    user_id: UUID = Depends(get_current_user_id),
    service: CandidateService = Depends(get_candidate_service),
):
    try:
        candidate = await service.create_candidate(user_id, data)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return candidate


@router.get("/me", response_model=CandidateRead)
async def get_my_candidate(
    user_id: UUID = Depends(get_current_user_id),
    service: CandidateService = Depends(get_candidate_service),
):
    try:
        candidate = await service.get_my_candidate(user_id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return candidate


@router.get("/{candidate_id}", response_model=CandidateRead)
async def get_candidate(
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: CandidateService = Depends(get_candidate_service),
):
    try:
        candidate = await service.get_candidate(candidate_id, user_id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return candidate


@router.put("/{candidate_id}", response_model=CandidateRead)
async def update_candidate(
    candidate_id: UUID,
    data: CandidateUpdate,
    user_id: UUID = Depends(get_current_user_id),
    service: CandidateService = Depends(get_candidate_service),
):
    try:
        candidate = await service.update_candidate(candidate_id, user_id, data)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return candidate


@router.delete("/{candidate_id}", response_model=CandidateRead)
async def delete_candidate(
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: CandidateService = Depends(get_candidate_service),
):
    try:
        candidate = await service.deactivate_candidate(candidate_id, user_id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return candidate


@router.put("/{candidate_id}/preferences", response_model=CandidateRead)
async def update_preferences(
    candidate_id: UUID,
    data: CareerPreferences,
    user_id: UUID = Depends(get_current_user_id),
    service: CandidateService = Depends(get_candidate_service),
):
    try:
        candidate = await service.update_preferences(candidate_id, user_id, data)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return candidate


@router.get("/{candidate_id}/profile", response_model=ProfileRead)
async def get_profile(
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ProfileService = Depends(get_profile_service),
):
    # Ownership enforced by profile service lookup via user_id.
    try:
        profile = await service.get_profile(user_id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return profile
