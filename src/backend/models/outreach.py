"""Recruiter / professional outreach models.

Outreach drafts and sends are candidate-scoped messages to VERIFIED recruiter
contacts (``RecruiterContact``). Hard safety boundaries:

* A draft is only ever grounded in verified candidate facts plus verified
  contact/job information (deterministic writer + grounding validator).
* Contact identity is never fabricated: ``DraftOutreach`` references a
  ``RecruiterContact`` that already cleared the VERIFIED + confidence >= 70
  surface gate.
* Sending requires an APPROVED human approval (``Approval`` of kind
  ``outreach_send``), a verified destination address, a non-suppressed
  contact, and respects the per-candidate daily send cap.
* Message edits append version rows (``OutreachMessageVersion``) so the send
  history is auditable; at most one non-terminal ``OutreachRun`` may exist per
  message (partial unique index), so a message can never be sent twice
  concurrently.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import JSON, Boolean, Column, DateTime, Index, Integer, String, Text, text
from sqlmodel import Field, Relationship

from backend.db.base import IdModel

if TYPE_CHECKING:
    from backend.models.candidate import Candidate
    from backend.models.job import Job
    from backend.models.learning import Feedback
    from backend.models.recruiter_contact import RecruiterContact


class OutreachChannel(str, Enum):
    """Communication channel for an outreach message."""

    EMAIL = "email"
    PROFESSIONAL_NETWORK = "professional_network"


class OutreachStatus(str, Enum):
    """Lifecycle of one outreach message."""

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResponseStatus(str, Enum):
    """Whether the recipient replied."""

    NO_RESPONSE = "no_response"
    RESPONDED = "responded"


class OutreachRunStatus(str, Enum):
    """Lifecycle of one send attempt workflow."""

    PENDING = "pending"
    RUNNING = "running"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OutreachMessage(IdModel, table=True):
    """A single candidate-scoped outreach message (initial or follow-up)."""

    __tablename__ = "outreach_messages"

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    contact_id: UUID = Field(
        foreign_key="recruiter_contacts.id", nullable=False, index=True
    )
    job_id: UUID | None = Field(foreign_key="jobs.id", nullable=True, index=True)
    application_id: UUID | None = Field(
        foreign_key="applications.id", nullable=True, index=True
    )
    parent_id: UUID | None = Field(
        foreign_key="outreach_messages.id", nullable=True, index=True
    )

    channel: OutreachChannel = Field(default=OutreachChannel.EMAIL, index=True)
    subject: str = Field(sa_column=Column(String(255), nullable=False))
    body: str = Field(sa_column=Column(Text, nullable=False))

    status: OutreachStatus = Field(default=OutreachStatus.DRAFT, index=True)
    response_status: ResponseStatus = Field(
        default=ResponseStatus.NO_RESPONSE, index=True
    )

    is_follow_up: bool = Field(
        sa_column=Column(Boolean, nullable=False, server_default="0"), default=False
    )
    approval_id: UUID | None = Field(sa_column=Column(String(36), nullable=True, index=True))

    rules_version: str | None = Field(sa_column=Column(String(32), nullable=True))
    fact_sources: list[dict[str, object]] | None = Field(
        default_factory=list, sa_column=Column(JSON, default=list)
    )

    sent_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    responded_at: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    # Opaque provider-side message id (never a secret/token).
    provider_message_id: str | None = Field(sa_column=Column(String(255), nullable=True))
    last_error: str | None = Field(sa_column=Column(Text, nullable=True))

    candidate: "Candidate" = Relationship(back_populates="outreach_messages")
    contact: "RecruiterContact" = Relationship(back_populates="outreach_messages")
    job: Optional["Job"] = Relationship(back_populates="outreach_messages")
    versions: list["OutreachMessageVersion"] = Relationship(
        back_populates="message",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    runs: list["OutreachRun"] = Relationship(
        back_populates="message",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    feedbacks: list["Feedback"] = Relationship(back_populates="outreach_message")


class OutreachMessageVersion(IdModel, table=True):
    """Append-only snapshot of a message subject/body per edit.

    ``version_number`` increments per message; the first write is the generated
    draft state. Rows preserve the exact subject/body the message held so the
    send history and any human edits stay auditable.
    """

    __tablename__ = "outreach_message_versions"
    __table_args__ = (
        Index(
            "uq_outreach_message_versions_number",
            "message_id",
            "version_number",
            unique=True,
        ),
    )

    message_id: UUID = Field(foreign_key="outreach_messages.id", nullable=False, index=True)
    version_number: int = Field(sa_column=Column(Integer, nullable=False, server_default="1"))
    subject: str = Field(sa_column=Column(String(255), nullable=False))
    body: str = Field(sa_column=Column(Text, nullable=False))
    is_generated: bool = Field(
        sa_column=Column(Boolean, nullable=False, server_default="0"), default=False
    )
    change_reason: str | None = Field(sa_column=Column(Text, nullable=True))
    fact_sources: list[dict[str, object]] | None = Field(
        default_factory=list, sa_column=Column(JSON, default=list)
    )
    created_by: str | None = Field(sa_column=Column(String(36), nullable=True))

    message: OutreachMessage = Relationship(back_populates="versions")


class OutreachRun(IdModel, table=True):
    """Durable record of one outreach send workflow.

    At most one non-terminal run exists per message (partial unique index), so
    concurrent sends can never double-submit. Retries are bounded by
    ``max_attempts`` with exponential backoff scheduled on ``next_retry_at``.
    """

    __tablename__ = "outreach_runs"
    __table_args__ = (
        Index(
            "uq_outreach_runs_open_message",
            "message_id",
            unique=True,
            sqlite_where=text("status IN ('PENDING', 'RUNNING')"),
            postgresql_where=text("status IN ('PENDING', 'RUNNING')"),
        ),
    )

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    message_id: UUID = Field(foreign_key="outreach_messages.id", nullable=False, index=True)

    status: OutreachRunStatus = Field(default=OutreachRunStatus.PENDING, index=True)
    attempt_count: int = Field(
        sa_column=Column(Integer, nullable=False, server_default="0"), default=0
    )
    max_attempts: int = Field(
        sa_column=Column(Integer, nullable=False, server_default="3"), default=3
    )
    next_retry_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    last_error: str | None = Field(sa_column=Column(Text, nullable=True))
    result_metadata: dict[str, object] = Field(
        default_factory=dict, sa_column=Column(JSON, default=dict)
    )

    started_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": False},  # type: ignore[call-overload]
    )
    sent_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    finished_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    provider_message_id: str | None = Field(sa_column=Column(String(255), nullable=True))

    candidate: "Candidate" = Relationship(back_populates="outreach_runs")
    message: OutreachMessage = Relationship(back_populates="runs")
