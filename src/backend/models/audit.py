"""Audit event model."""

from uuid import UUID

from sqlalchemy import JSON, Column, String, Text
from sqlmodel import Field

from backend.db.base import IdModel


class AuditEvent(IdModel, table=True):
    """Append-only audit log."""

    __tablename__ = "audit_events"

    event_type: str = Field(sa_column=Column(String(128), nullable=False, index=True))
    actor_id: UUID | None = Field(sa_column=Column(String(36), nullable=True, index=True))
    candidate_id: UUID | None = Field(sa_column=Column(String(36), nullable=True, index=True))
    entity_type: str | None = Field(sa_column=Column(String(128), nullable=True))
    entity_id: UUID | None = Field(sa_column=Column(String(36), nullable=True))
    result: str = Field(default="success", sa_column=Column(String(32), nullable=False))
    request_id: str | None = Field(sa_column=Column(String(64), nullable=True, index=True))
    event_metadata: dict[str, object] = Field(
        default_factory=dict, sa_column=Column(JSON, default=dict)
    )
    details: str | None = Field(sa_column=Column(Text, nullable=True))
