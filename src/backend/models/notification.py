"""Notification models for dashboard alerts (Phase 10).

Notifications are in-app-first; email/SMS channels are declarative and can be
routed through a pluggable transport later. Security alerts bypass preference
muting, and every notification carries an explicit entity reference so the UI
can navigate to the source while the user retains control via preferences.
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, Relationship

from backend.db.base import IdModel

if TYPE_CHECKING:
    from backend.models.candidate import Candidate


class NotificationCategory(str, Enum):
    NEW_MATCH = "new_match"
    APPROVAL_NEEDED = "approval_needed"
    APPLICATION_UPDATE = "application_update"
    OUTREACH_RESPONSE = "outreach_response"
    SECURITY_EVENT = "security_event"
    ERROR = "error"


class NotificationChannel(str, Enum):
    IN_APP = "in_app"
    EMAIL = "email"
    SMS = "sms"


class NotificationStatus(str, Enum):
    UNREAD = "unread"
    READ = "read"
    ARCHIVED = "archived"


class Notification(IdModel, table=True):
    __tablename__ = "notifications"

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    category: NotificationCategory = Field(
        sa_column=Column(
            SAEnum(NotificationCategory, values_callable=lambda e: [m.value for m in e], native_enum=False),
            nullable=False,
            server_default="ERROR",
            index=True,
        ),
        default=NotificationCategory.ERROR,
    )
    channel: NotificationChannel = Field(
        sa_column=Column(
            SAEnum(NotificationChannel, values_callable=lambda e: [m.value for m in e], native_enum=False),
            nullable=False,
            server_default="IN_APP",
            index=True,
        ),
        default=NotificationChannel.IN_APP,
    )
    status: NotificationStatus = Field(
        sa_column=Column(
            SAEnum(NotificationStatus, values_callable=lambda e: [m.value for m in e], native_enum=False),
            nullable=False,
            server_default="UNREAD",
            index=True,
        ),
        default=NotificationStatus.UNREAD,
    )
    title: str = Field(sa_column=Column(String(255), nullable=False))
    detail: str = Field(sa_column=Column(Text, nullable=False))
    entity_type: str | None = Field(sa_column=Column(String(128), nullable=True))
    entity_id: str | None = Field(sa_column=Column(String(36), nullable=True))
    read_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))

    candidate: Optional["Candidate"] = Relationship(back_populates="notifications")


class NotificationPreference(IdModel, table=True):
    __tablename__ = "notification_preferences"

    candidate_id: UUID = Field(
        foreign_key="candidates.id", nullable=False, unique=True, index=True
    )
    in_app_enabled: bool = Field(default=True)
    email_enabled: bool = Field(default=True)
    sms_enabled: bool = Field(default=False)
    new_match_enabled: bool = Field(default=True)
    approval_needed_enabled: bool = Field(default=True)
    application_update_enabled: bool = Field(default=True)
    outreach_response_enabled: bool = Field(default=True)
    error_enabled: bool = Field(default=True)

    candidate: Optional["Candidate"] = Relationship(back_populates="notification_preferences")
