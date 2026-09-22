"""Notifications router (in-app alerts + preferences)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from backend.api.deps import get_notification_service, handle_domain_error
from backend.core.exceptions import NotFoundError, ValidationError
from backend.models.notification import NotificationCategory, NotificationStatus
from backend.schemas.notifications import (
    MarkAllReadResponse,
    NotificationListResponse,
    NotificationPreferenceRead,
    NotificationPreferenceUpdate,
    NotificationRead,
    UnreadCountResponse,
)
from backend.services.notifications import NotificationService

router = APIRouter(prefix="/candidates/{candidate_id}", tags=["notifications"])


def _read(notification) -> NotificationRead:
    return NotificationRead.model_validate(notification)


@router.get("/notifications", response_model=NotificationListResponse)
async def list_notifications(
    candidate_id: UUID,
    notification_status: NotificationStatus | None = Query(default=None, alias="status"),
    category: NotificationCategory | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationListResponse:
    try:
        items, total = await service.list(
            status=notification_status,
            category=category,
            limit=limit,
            offset=offset,
        )
    except (NotFoundError, ValidationError) as exc:
        raise handle_domain_error(exc) from exc
    return NotificationListResponse(items=[_read(n) for n in items], total=total)


@router.get("/notifications/unread-count", response_model=UnreadCountResponse)
async def unread_count(
    candidate_id: UUID,
    service: NotificationService = Depends(get_notification_service),
) -> UnreadCountResponse:
    try:
        count = await service.unread_count()
    except (NotFoundError, ValidationError) as exc:
        raise handle_domain_error(exc) from exc
    return UnreadCountResponse(count=count)


@router.post("/notifications/{notification_id}/read", response_model=NotificationRead)
async def mark_notification_read(
    candidate_id: UUID,
    notification_id: UUID,
    service: NotificationService = Depends(get_notification_service),
) -> NotificationRead:
    try:
        notification = await service.mark_read(notification_id)
    except (NotFoundError, ValidationError) as exc:
        raise handle_domain_error(exc) from exc
    return _read(notification)


@router.post("/notifications/read-all", response_model=MarkAllReadResponse)
async def mark_all_read(
    candidate_id: UUID,
    service: NotificationService = Depends(get_notification_service),
) -> MarkAllReadResponse:
    try:
        updated = await service.mark_all_read()
    except (NotFoundError, ValidationError) as exc:
        raise handle_domain_error(exc) from exc
    return MarkAllReadResponse(updated=updated)


@router.get("/notifications/preferences", response_model=NotificationPreferenceRead)
async def get_preferences(
    candidate_id: UUID,
    service: NotificationService = Depends(get_notification_service),
) -> NotificationPreferenceRead:
    try:
        prefs = await service.get_preferences()
    except (NotFoundError, ValidationError) as exc:
        raise handle_domain_error(exc) from exc
    return NotificationPreferenceRead.model_validate(prefs)


@router.put("/notifications/preferences", response_model=NotificationPreferenceRead)
async def update_preferences(
    candidate_id: UUID,
    payload: NotificationPreferenceUpdate,
    service: NotificationService = Depends(get_notification_service),
) -> NotificationPreferenceRead:
    try:
        prefs = await service.update_preferences(payload)
    except (NotFoundError, ValidationError) as exc:
        raise handle_domain_error(exc) from exc
    return NotificationPreferenceRead.model_validate(prefs)
