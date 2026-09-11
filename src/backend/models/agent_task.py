"""Agent task model tracking asynchronous discovery/heart-work executions."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import JSON, Column, DateTime, String, Text
from sqlmodel import Field

from backend.db.base import IdModel


class AgentTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    AWAITING_APPROVAL = "awaiting_approval"
    CANCELLED = "cancelled"


class AgentTask(IdModel, table=True):
    """A single unit of agent work (e.g. a job-discovery run per candidate).

    Tracks lifecycle, retries, and an opaque result so runs are observable and
    idempotent at the record level. `entity_type`/`entity_id` and `task_type`
    are free-form keys chosen by the caller (e.g. task_type="job_discovery",
    entity_type="candidate").
    """

    __tablename__ = "agent_tasks"

    candidate_id: UUID | None = Field(foreign_key="candidates.id", nullable=True, index=True)
    task_type: str = Field(sa_column=Column(String(64), nullable=False, index=True))
    entity_type: str | None = Field(sa_column=Column(String(64), nullable=True))
    entity_id: UUID | None = Field(nullable=True, index=True)

    status: AgentTaskStatus = Field(default=AgentTaskStatus.PENDING, index=True)
    retry_count: int = Field(default=0)
    max_retries: int = Field(default=2)
    scheduled_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    started_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    finished_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    error_message: str | None = Field(sa_column=Column(Text, nullable=True))
    result_metadata: dict[str, object] = Field(
        default_factory=dict, sa_column=Column(JSON, default=dict)
    )
