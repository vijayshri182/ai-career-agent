"""Browser session abstraction model.

Records browser sessions the agent may use for a site. Raw cookies are never
persisted here — only an opaque reference to encrypted browser-state storage
(which must live outside the application database or in an encrypted store).
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Column, DateTime, String
from sqlmodel import Field, Relationship

from backend.db.base import IdModel

if TYPE_CHECKING:
    from backend.models.authentication import AuthProvider
    from backend.models.candidate import Candidate


class BrowserSessionStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CLOSED = "closed"
    SUSPENDED = "suspended"
    UNKNOWN = "unknown"


class BrowserSession(IdModel, table=True):
    __tablename__ = "browser_sessions"

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    provider_id: UUID = Field(foreign_key="auth_providers.id", nullable=False, index=True)
    status: BrowserSessionStatus = Field(default=BrowserSessionStatus.ACTIVE, index=True)
    # Opaque pointer to encrypted browser-state storage; never raw cookies.
    storage_reference: str | None = Field(sa_column=Column(String(512), nullable=True))
    # Opaque session identifier as reported by the external site (reference only).
    external_session_id: str | None = Field(sa_column=Column(String(512), nullable=True))
    last_seen_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    closed_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))

    candidate: "Candidate" = Relationship(back_populates="browser_sessions")
    provider: "AuthProvider" = Relationship(back_populates="browser_sessions")
