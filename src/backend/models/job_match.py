"""Job match result model produced by the explainable matching engine.

One row per (candidate, job). Re-evaluation updates the row in place, so
evaluation is idempotent at the record level while retaining provenance
(evaluated_at, rules_version, full score breakdown snapshot) for auditability.
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import JSON, Column, DateTime, Float, String
from sqlmodel import Field, Relationship, UniqueConstraint

from backend.db.base import IdModel

if TYPE_CHECKING:
    from backend.models.candidate import Candidate
    from backend.models.job import Job


class JobMatchStatus(str, Enum):
    PENDING = "pending"
    MATCHED = "matched"
    REJECTED = "rejected"


class JobMatch(IdModel, table=True):
    __tablename__ = "job_matches"
    __table_args__ = (
        UniqueConstraint("candidate_id", "job_id", name="uq_job_matches_candidate_job"),
    )

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    job_id: UUID = Field(foreign_key="jobs.id", nullable=False, index=True)

    status: JobMatchStatus = Field(default=JobMatchStatus.PENDING, index=True)
    score: float = Field(sa_column=Column(Float, nullable=False))
    confidence: float = Field(sa_column=Column(Float, nullable=False))
    is_match: bool = Field(default=False, index=True)

    matched_skills: list[str] = Field(default_factory=list, sa_column=Column(JSON, default=list))
    missing_skills: list[str] = Field(default_factory=list, sa_column=Column(JSON, default=list))
    transferable_skills: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, default=list)
    )

    strengths: list[str] = Field(default_factory=list, sa_column=Column(JSON, default=list))
    gaps: list[str] = Field(default_factory=list, sa_column=Column(JSON, default=list))
    blockers: list[str] = Field(default_factory=list, sa_column=Column(JSON, default=list))
    recommendation_reasons: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, default=list)
    )
    rejection_reasons: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, default=list)
    )

    score_breakdown: dict[str, object] = Field(
        default_factory=dict, sa_column=Column(JSON, default=dict)
    )
    rules_version: str = Field(sa_column=Column(String(64), nullable=False))
    evaluated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))

    candidate: "Candidate" = Relationship(back_populates="job_matches")
    job: "Job" = Relationship(back_populates="matches")
