"""Human-in-the-loop challenge model.

Challenges are the durable record that an external site asked for human
verification (CAPTCHA, MFA/OTP, login, bot protection, ...). They never store
solutions, answers, passwords, OTPs, or tokens. Resolving a challenge is always
a *human* act in a real browser or via the site's own flow; the system only
records the outcome.

A partial unique index guarantees idempotency: at most one in-flight challenge
of the same type may exist per provider (open/acknowledged/human-action states).
"""

from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, Text, text
from sqlmodel import Field, Relationship

from backend.db.base import IdModel

if TYPE_CHECKING:
    from backend.models.authentication import AuthProvider
    from backend.models.candidate import Candidate


class ChallengeType(str, Enum):
    """Kind of human verification requested by a site."""

    CAPTCHA = "captcha"
    MFA = "mfa"
    OTP = "otp"
    LOGIN_REQUIRED = "login_required"
    SESSION_EXPIRED = "session_expired"
    BOT_PROTECTION = "bot_protection"
    ACCESS_DENIED = "access_denied"
    RATE_LIMIT = "rate_limit"
    UNKNOWN_HUMAN_VERIFICATION = "unknown_human_verification"


class ChallengeStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    HUMAN_ACTION_REQUIRED = "human_action_required"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    FAILED = "failed"


class ChallengeSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ChallengeResolution(str, Enum):
    """How a challenge was closed."""

    HUMAN = "human"
    SUPERSEDED = "superseded"
    SYSTEM = "system"
    UNRESOLVED = "unresolved"


class Challenge(IdModel, table=True):
    __tablename__ = "challenges"
    __table_args__ = (
        # Idempotency guard: one in-flight challenge per (provider, type).
        Index(
            "uq_challenges_open_provider_type",
            "provider_id",
            "challenge_type",
            unique=True,
            sqlite_where=text(
                "status IN ('open', 'acknowledged', 'human_action_required')"
            ),
            postgresql_where=text(
                "status IN ('open', 'acknowledged', 'human_action_required')"
            ),
        ),
    )

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    provider_id: UUID = Field(foreign_key="auth_providers.id", nullable=False, index=True)
    # Soft reference to workflow_runs.id (created alongside the challenge).
    workflow_id: UUID | None = Field(sa_column=Column(String(36), nullable=True, index=True))

    challenge_type: ChallengeType = Field(default=ChallengeType.UNKNOWN_HUMAN_VERIFICATION)
    status: ChallengeStatus = Field(default=ChallengeStatus.OPEN, index=True)
    severity: ChallengeSeverity = Field(default=ChallengeSeverity.MEDIUM)
    human_required: bool = Field(default=True)
    description: str | None = Field(sa_column=Column(Text, nullable=True))
    context_metadata: dict[str, object] = Field(
        default_factory=dict, sa_column=Column(JSON, default=dict)
    )

    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": False},  # type: ignore[call-overload]
    )
    acknowledged_at: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    expires_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    resolved_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    cancelled_at: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    timed_out_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    resolution_method: ChallengeResolution | None = Field(
        sa_column=Column(String(32), nullable=True)
    )

    retry_count: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    max_retries: int = Field(default=2, sa_column=Column(Integer, nullable=False))

    candidate: "Candidate" = Relationship(back_populates="challenges")
    provider: "AuthProvider" = Relationship(back_populates="challenges")
