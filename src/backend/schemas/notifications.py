"""Notification schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.models.notification import (
    NotificationCategory,
    NotificationChannel,
    NotificationStatus,
)


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    category: NotificationCategory
    channel: NotificationChannel
    status: NotificationStatus
    title: str
    detail: str
    entity_type: str | None
    entity_id: str | None
    created_at: datetime
    read_at: datetime | None


class NotificationListResponse(BaseModel):
    items: list[NotificationRead]
    total: int


class UnreadCountResponse(BaseModel):
    count: int


class NotificationPreferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    in_app_enabled: bool
    email_enabled: bool
    sms_enabled: bool
    new_match_enabled: bool
    approval_needed_enabled: bool
    application_update_enabled: bool
    outreach_response_enabled: bool
    error_enabled: bool


class NotificationPreferenceUpdate(BaseModel):
    in_app_enabled: bool | None = Field(default=None)
    email_enabled: bool | None = Field(default=None)
    sms_enabled: bool | None = Field(default=None)
    new_match_enabled: bool | None = Field(default=None)
    approval_needed_enabled: bool | None = Field(default=None)
    application_update_enabled: bool | None = Field(default=None)
    outreach_response_enabled: bool | None = Field(default=None)
    error_enabled: bool | None = Field(default=None)


class MarkAllReadResponse(BaseModel):
    updated: int
