"""Job matching router (deterministic, explainable matching engine)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from backend.api.deps import (
    get_current_user_id,
    get_job_matching_service,
    get_owned_candidate,
    handle_domain_error,
)
from backend.models.job_match import JobMatchStatus
from backend.schemas.matching import BatchMatchResult, JobMatchRead, MatchListResponse
from backend.services.matching import JobMatchingService

router = APIRouter(prefix="/candidates/{candidate_id}", tags=["job-matching"])


@router.post(
    "/jobs/{job_id}/match",
    response_model=JobMatchRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def evaluate_job(
    candidate_id: UUID,
    job_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: JobMatchingService = Depends(get_job_matching_service),
):
    try:
        return await service.evaluate(candidate_id, user_id, job_id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get(
    "/jobs/{job_id}/match",
    response_model=JobMatchRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def get_job_match(
    candidate_id: UUID,
    job_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: JobMatchingService = Depends(get_job_matching_service),
):
    try:
        return await service.get_for_job(candidate_id, user_id, job_id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post(
    "/matching/evaluate",
    response_model=BatchMatchResult,
    dependencies=[Depends(get_owned_candidate)],
)
async def batch_evaluate(
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    limit: int = Query(default=50, ge=1, le=500),
    recompute: bool = Query(default=False),
    service: JobMatchingService = Depends(get_job_matching_service),
):
    try:
        return await service.batch_evaluate(candidate_id, user_id, limit=limit, recompute=recompute)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get(
    "/matches",
    response_model=MatchListResponse,
    dependencies=[Depends(get_owned_candidate)],
)
async def list_matches(
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    is_match: bool | None = Query(default=None),
    status_filter: JobMatchStatus | None = Query(default=None, alias="status"),
    min_score: float | None = Query(default=None, ge=0, le=100),
    sort: str = Query(default="score"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: JobMatchingService = Depends(get_job_matching_service),
):
    try:
        return await service.list(
            candidate_id,
            user_id,
            is_match=is_match,
            status=status_filter,
            min_score=min_score,
            sort=sort,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        raise handle_domain_error(exc) from exc
