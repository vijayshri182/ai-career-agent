"""Application automation run model.

An ``AutomationRun`` is the durable, candidate-scoped record of one application
submission workflow. A run may only be created after (a) the job's source
explicitly permits automation and (b) an APPROVED human approval for exactly
that application exists. At most one non-terminal run may exist per application
(partial unique index), so a submission can never be launched twice
concurrently. Runs pause for human challenges (CAPTCHA/MFA/bot protection) and
retry within an explicit attempt budget with exponential backoff scheduling.

Nothing here stores or passes secrets, tokens, or session material — the run
only records opaque references (provider id, challenge id, workflow id).
"""

from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, Text, text
from sqlmodel import Field, Relationship

from backend.db.base import IdModel

if TYPE_CHECKING:
    from backend.models.application import Application
    from backend.models.candidate import Candidate


class AutomationRunStatus(str, Enum):
    """Lifecycle of one application submission workflow."""

    PENDING = "pending"
    RUNNING = "running"
    SUBMITTED = "submitted"
    PAUSED_HUMAN_ACTION = "paused_human_action"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AutomationRun(IdModel, table=True):
    __tablename__ = "automation_runs"
    __table_args__ = (
        # Idempotency guard: at most one non-terminal run per application.
        Index(
            "uq_automation_runs_open_app",
            "application_id",
            unique=True,
            sqlite_where=text("status IN ('pending', 'running', 'paused_human_action')"),
            postgresql_where=text("status IN ('pending', 'running', 'paused_human_action')"),
        ),
    )

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    application_id: UUID = Field(foreign_key="applications.id", nullable=False, index=True)
    provider_id: UUID | None = Field(foreign_key="auth_providers.id", nullable=True, index=True)

    # Soft references (never secrets) to the human-in-the-loop records.
    challenge_id: UUID | None = Field(sa_column=Column(String(36), nullable=True, index=True))
    workflow_id: UUID | None = Field(sa_column=Column(String(36), nullable=True, index=True))

    status: AutomationRunStatus = Field(
        sa_column=Column(String(24), nullable=False, server_default="pending"),
        default=AutomationRunStatus.PENDING,
    )
    attempt_count: int = Field(
        sa_column=Column(Integer, nullable=False, server_default="0"), default=0
    )
    max_attempts: int = Field(
        sa_column=Column(Integer, nullable=False, server_default="3"), default=3
    )

    next_retry_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    last_error: str | None = Field(sa_column=Column(Text, nullable=True))

    context_metadata: dict[str, object] = Field(
        default_factory=dict, sa_column=Column(JSON, default=dict)
    )
    result_metadata: dict[str, object] = Field(
        default_factory=dict, sa_column=Column(JSON, default=dict)
    )

    started_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": False},  # type: ignore[call-overload]
    )
    submitted_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    finished_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))

    candidate: "Candidate" = Relationship(back_populates="automation_runs")
    application: "Application" = Relationship(back_populates="automation_runs")
