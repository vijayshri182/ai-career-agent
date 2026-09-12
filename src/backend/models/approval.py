"""Human approval workflow models.

External actions (submitting an application, sending outreach) require an
explicit human decision first. An ``Approval`` tracks one requested decision;
every decision is recorded as an append-only ``ApprovalDecision`` and mirrored
to the generic audit log.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlmodel import Field, Relationship

from backend.db.base import IdModel

if TYPE_CHECKING:
    from backend.models.candidate import Candidate


class ApprovalKind(str, Enum):
    APPLICATION_SUBMISSION = "application_submission"
    OUTREACH_SEND = "outreach_send"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SNOOZED = "snoozed"
    CANCELLED = "cancelled"


class ApprovalDecisionType(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"
    SNOOZE = "snooze"
    CANCEL = "cancel"


class Approval(IdModel, table=True):
    __tablename__ = "approvals"

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    kind: ApprovalKind = Field(default=ApprovalKind.APPLICATION_SUBMISSION)
    status: ApprovalStatus = Field(default=ApprovalStatus.PENDING)
    target_type: str = Field(sa_column=Column(String(30), nullable=False))
    target_id: UUID = Field(sa_column=Column(Uuid(as_uuid=True), nullable=False, index=True))
    application_id: UUID | None = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("applications.id"),
            nullable=True,
        )
    )
    autonomy_level: int = Field(
        default=2, sa_column=Column(Integer, nullable=False, server_default="2")
    )
    summary: str | None = Field(sa_column=Column(Text, nullable=True))
    context: dict[str, object] | None = Field(
        default_factory=dict, sa_column=Column(JSON, default=dict)
    )
    decided_by: UUID | None = Field(sa_column=Column(String(36), nullable=True))
    decided_at: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    decision_type: ApprovalDecisionType | None = Field(default=None)
    decision_note: str | None = Field(sa_column=Column(Text, nullable=True))
    snoozed_until: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    candidate: Optional["Candidate"] = Relationship(back_populates="approvals")
    decisions: list["ApprovalDecision"] = Relationship(
        back_populates="approval",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class ApprovalDecision(IdModel, table=True):
    """Append-only record of a single human/actor decision on an approval."""

    __tablename__ = "approval_decisions"

    approval_id: UUID = Field(foreign_key="approvals.id", nullable=False, index=True)
    actor_id: UUID | None = Field(sa_column=Column(String(36), nullable=True, index=True))
    decision_type: ApprovalDecisionType = Field(nullable=False)
    note: str | None = Field(sa_column=Column(Text, nullable=True))
    decided_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=__import__("sqlalchemy").func.now()
        ),
    )

    approval: Approval = Relationship(back_populates="decisions")
