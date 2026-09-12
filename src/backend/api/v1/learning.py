"""Learning / optimization router (feedback + analytics + recommendations)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from backend.api.deps import get_analytics_service
from backend.core.exceptions import NotFoundError, ValidationError
from backend.models.learning import FeedbackOutcome, RecommendationKind, RecommendationStatus
from backend.schemas.learning import (
    AnalyticsSummary,
    FeedbackCreate,
    FeedbackListResponse,
    FeedbackRead,
    RecommendationListResponse,
    RecommendationRead,
)
from backend.services.analytics import AnalyticsService

router = APIRouter(prefix="/candidates/{candidate_id}", tags=["analytics"])


def _feedback_read(feedback) -> FeedbackRead:
    return FeedbackRead.model_validate(feedback)


def _recommendation_read(recommendation) -> RecommendationRead:
    return RecommendationRead.model_validate(recommendation)


@router.post(
    "/feedback",
    response_model=FeedbackRead,
    status_code=status.HTTP_201_CREATED,
)
async def record_feedback(
    candidate_id: UUID,
    payload: FeedbackCreate,
    service: AnalyticsService = Depends(get_analytics_service),
) -> FeedbackRead:
    try:
        feedback = await service.add_feedback(
            outcome=payload.outcome,
            application_id=payload.application_id,
            outreach_message_id=payload.outreach_message_id,
            stage=payload.stage,
            note=payload.note,
        )
    except (NotFoundError, ValidationError) as exc:
        from backend.api.deps import handle_domain_error

        raise handle_domain_error(exc) from exc
    return _feedback_read(feedback)


@router.get("/feedback", response_model=FeedbackListResponse)
async def list_feedback(
    candidate_id: UUID,
    outcome: FeedbackOutcome | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: AnalyticsService = Depends(get_analytics_service),
) -> FeedbackListResponse:
    try:
        items, total = await service.list_feedback(
            outcome=outcome, limit=limit, offset=offset
        )
    except (NotFoundError, ValidationError) as exc:
        from backend.api.deps import handle_domain_error

        raise handle_domain_error(exc) from exc
    return FeedbackListResponse(items=[_feedback_read(f) for f in items], total=total)


@router.get("/analytics/summary", response_model=AnalyticsSummary)
async def analytics_summary(
    candidate_id: UUID,
    service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsSummary:
    try:
        return await service.summary()
    except (NotFoundError, ValidationError) as exc:
        from backend.api.deps import handle_domain_error

        raise handle_domain_error(exc) from exc


@router.post("/recommendations/generate", response_model=RecommendationListResponse)
async def generate_recommendations(
    candidate_id: UUID,
    refresh: bool = Query(default=False),
    service: AnalyticsService = Depends(get_analytics_service),
) -> RecommendationListResponse:
    try:
        items = await service.generate_recommendations(refresh=refresh)
    except (NotFoundError, ValidationError) as exc:
        from backend.api.deps import handle_domain_error

        raise handle_domain_error(exc) from exc
    return RecommendationListResponse(items=[_recommendation_read(r) for r in items], total=len(items))


@router.get("/recommendations", response_model=RecommendationListResponse)
async def list_recommendations(
    candidate_id: UUID,
    status_filter: RecommendationStatus | None = Query(default=None, alias="status"),
    kind: RecommendationKind | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: AnalyticsService = Depends(get_analytics_service),
) -> RecommendationListResponse:
    try:
        items, total = await service.list_recommendations(
            status=status_filter, kind=kind, limit=limit, offset=offset
        )
    except (NotFoundError, ValidationError) as exc:
        from backend.api.deps import handle_domain_error

        raise handle_domain_error(exc) from exc
    return RecommendationListResponse(
        items=[_recommendation_read(r) for r in items], total=total
    )


@router.post("/recommendations/{recommendation_id}/acknowledge", response_model=RecommendationRead)
async def acknowledge_recommendation(
    candidate_id: UUID,
    recommendation_id: UUID,
    service: AnalyticsService = Depends(get_analytics_service),
) -> RecommendationRead:
    try:
        recommendation = await service.acknowledge(recommendation_id)
    except (NotFoundError, ValidationError) as exc:
        from backend.api.deps import handle_domain_error

        raise handle_domain_error(exc) from exc
    return _recommendation_read(recommendation)


@router.post("/recommendations/{recommendation_id}/archive", response_model=RecommendationRead)
async def archive_recommendation(
    candidate_id: UUID,
    recommendation_id: UUID,
    service: AnalyticsService = Depends(get_analytics_service),
) -> RecommendationRead:
    try:
        recommendation = await service.archive(recommendation_id)
    except (NotFoundError, ValidationError) as exc:
        from backend.api.deps import handle_domain_error

        raise handle_domain_error(exc) from exc
    return _recommendation_read(recommendation)
