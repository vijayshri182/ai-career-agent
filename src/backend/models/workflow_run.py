"""Human-in-the-loop workflow run model.

A persistent record of a workflow that paused because an external site required
human verification. State transitions are enforced by the workflow state
machine in services.human_in_loop. Resume is idempotent and guarded by an
opaque resume token; retries are capped by max_attempts so an unresolved
challenge can never trigger an endless resume loop.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, DateTime, Integer, String
from sqlmodel import Field, Relationship

from backend.db.base import IdModel

if TYPE_CHECKING:
    from backend.models.authentication import AuthProvider
    from backend.models.candidate import Candidate


class WorkflowStatus(str, Enum):
    RUNNING = "running"
    PAUSED_HUMAN_ACTION = "paused_human_action"
    RESUMED = "resumed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    FAILED = "failed"


class WorkflowRun(IdModel, table=True):
    __tablename__ = "workflow_runs"

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    provider_id: UUID = Field(foreign_key="auth_providers.id", nullable=False, index=True)
    workflow_type: str = Field(
        default="authentication_and_challenge", sa_column=Column(String(128), nullable=False)
    )
    status: WorkflowStatus = Field(default=WorkflowStatus.RUNNING, index=True)

    resume_token: UUID = Field(default_factory=uuid4, unique=True, index=True)
    attempt_count: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    max_attempts: int = Field(default=2, sa_column=Column(Integer, nullable=False))

    context_metadata: dict[str, object] = Field(
        default_factory=dict, sa_column=Column(JSON, default=dict)
    )

    started_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": False},  # type: ignore[call-overload]
    )
    paused_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    resumed_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    finished_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    expires_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))

    candidate: "Candidate" = Relationship(back_populates="workflow_runs")
    provider: "AuthProvider" = Relationship(back_populates="workflow_runs")
