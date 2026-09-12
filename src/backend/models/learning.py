"""Learning / optimization models.

Phase 12 captures post-submission outcomes and produces explainable, purely
suggestive recommendations so the system can learn which efforts pay off.

Hard safety boundaries:

* ``Feedback`` rows record *observed* outcomes (offer / interview / rejection /
  ghosted / withdrawn) plus the candidate's own note. They never infer a cause.
* ``Recommendation`` rows are *explanations, never edits*: every row carries a
  rationale list citing the exact candidate-owned data it was derived from, and
  no other table is ever touched by the learning service.
* Recommendations are generated only from neutral, candidate-owned signals
  (skills, matches, counts). No protected attribute is collected or used.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import JSON, Column, DateTime, String, Text
from sqlmodel import Field, Relationship, UniqueConstraint

from backend.db.base import IdModel

if TYPE_CHECKING:
    from backend.models.application import Application
    from backend.models.candidate import Candidate
    from backend.models.outreach import OutreachMessage


class FeedbackOutcome(str, Enum):
    """Observed outcome of an application / outreach conversation."""

    OFFER_RECEIVED = "offer_received"
    INTERVIEW_REQUESTED = "interview_requested"
    REJECTED = "rejected"
    GHOSTED = "ghosted"
    WITHDRAWN = "withdrawn"
    OTHER = "other"


class Feedback(IdModel, table=True):
    """Candidate-scoped record of one observed post-submission outcome."""

    __tablename__ = "feedbacks"

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    application_id: UUID | None = Field(
        foreign_key="applications.id", nullable=True, index=True
    )
    outreach_message_id: UUID | None = Field(
        foreign_key="outreach_messages.id", nullable=True, index=True
    )
    outcome: FeedbackOutcome = Field(default=FeedbackOutcome.OTHER, index=True)
    stage: str | None = Field(sa_column=Column(String(128), nullable=True))
    note: str | None = Field(sa_column=Column(Text, nullable=True))
    happened_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": False},  # type: ignore[call-overload]
    )

    candidate: Optional["Candidate"] = Relationship(back_populates="feedbacks")
    application: Optional["Application"] = Relationship(back_populates="feedbacks")
    outreach_message: Optional["OutreachMessage"] = Relationship(
        back_populates="feedbacks"
    )


class RecommendationKind(str, Enum):
    """Type of an action a candidate could take based on evidence."""

    SKILL_GAP = "skill_gap"
    PROFILE_IMPROVEMENT = "profile_improvement"
    APPLY_OPTIMIZATION = "apply_optimization"
    SOURCE_OPTIMIZATION = "source_optimization"
    OUTREACH_OPTIMIZATION = "outreach_optimization"


class RecommendationStatus(str, Enum):
    """Lifecycle of one recommendation row."""

    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    ARCHIVED = "archived"


class Recommendation(IdModel, table=True):
    """Explainable, purely suggestive recommendation derived from candidate data.

    ``rationale`` lists the exact candidate-owned facts (e.g. "Kubernetes appears
    in the missing-skills of 3 matching jobs"). Applying a recommendation never
    edits facts; the candidate acts on it through the normal profile APIs.
    """

    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id",
            "kind",
            "source_key",
            name="uq_recommendations_candidate_kind_key",
        ),
    )

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    kind: RecommendationKind = Field(index=True)
    source_key: str = Field(sa_column=Column(String(255), nullable=False))
    title: str = Field(sa_column=Column(String(255), nullable=False))
    detail: str = Field(sa_column=Column(Text, nullable=False))
    rationale: list[str] = Field(default_factory=list, sa_column=Column(JSON, default=list))
    status: RecommendationStatus = Field(default=RecommendationStatus.ACTIVE, index=True)

    candidate: Optional["Candidate"] = Relationship(back_populates="recommendations")
