"""CP15 eligibility and read-only match-evaluation schemas.

An explicit, testable eligibility decision is produced for every ACA-owned
Gate 4E ingestion record, then eligible records may be handed to the existing
(read-only) matching engine. Nothing here introduces scores, rankings, or
matching policy; reason codes are deterministic and auditable.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

GATE4E_ELIGIBILITY_POLICY_VERSION = 1


class Gate4eEligibilityStatus(str, Enum):
    """Outcome bucket for one ingestion record."""

    ELIGIBLE = "ELIGIBLE"
    EXCLUDED = "EXCLUDED"


class Gate4eEligibilityReason(str, Enum):
    """Deterministic eligibility reason codes (no scores/rankings)."""

    ELIGIBLE_VERIFIED = "ELIGIBLE_VERIFIED"
    ELIGIBLE_PARTIAL_WITH_URL_CONTROLLED = "ELIGIBLE_PARTIAL_WITH_URL_CONTROLLED"
    EXCLUDED_PARTIAL_NO_URL_QUARANTINED = "EXCLUDED_PARTIAL_NO_URL_QUARANTINED"
    EXCLUDED_UNRESOLVED_QUARANTINED = "EXCLUDED_UNRESOLVED_QUARANTINED"
    EXCLUDED_REJECTED_INVALID = "EXCLUDED_REJECTED_INVALID"
    EXCLUDED_PARTIAL_WITH_URL_POLICY_PENDING = "EXCLUDED_PARTIAL_WITH_URL_POLICY_PENDING"
    EXCLUDED_VERIFIED_INCOMPLETE_IDENTITY = "EXCLUDED_VERIFIED_INCOMPLETE_IDENTITY"
    EXCLUDED_NO_JOB = "EXCLUDED_NO_JOB"
    EXCLUDED_UNKNOWN_STATE = "EXCLUDED_UNKNOWN_STATE"


class Gate4eEligibilityDecision(BaseModel):
    """One auditable eligibility decision for one ingestion record."""

    model_config = ConfigDict(extra="forbid")

    alert_index: int | None = None
    gmail_message_id: str | None = None
    ingestion_identity: str | None = None
    posting_key: str | None = None
    job_id: UUID | None = None
    verification_status: str | None = None
    processing_status: str
    eligibility_status: Gate4eEligibilityStatus
    eligible_for_matching: bool
    reason_code: Gate4eEligibilityReason
    reason_detail: str
    missing_required_fields: list[str] = Field(default_factory=list)
    provenance_ref: str | None = None


class Gate4eEligibilityReport(BaseModel):
    """Deterministic eligibility overview for one candidate."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: UUID
    policy_version: int = GATE4E_ELIGIBILITY_POLICY_VERSION
    partial_with_url_policy: str
    evaluated_at: datetime | None = None
    total_records: int
    eligible_count: int
    excluded_count: int
    matching_invoked_count: int
    matching_not_invoked_count: int
    reason_counts: dict[str, int] = Field(default_factory=dict)
    decisions: list[Gate4eEligibilityDecision] = Field(default_factory=list)


class Gate4eMatchEvaluationOutcome(BaseModel):
    """Result of a read-only evaluation using the existing matching engine.

    ``score`` and ``breakdown`` are the unmodified output of the existing
    ``JobMatchScorer`` for transparency; the CP15 report omits scores/rankings.
    Nothing in this model is ever persisted by CP15.
    """

    model_config = ConfigDict(extra="ignore")

    job_id: UUID
    ingestion_identity: str | None = None
    rules_version: str | None = None
    score: float = 0.0
    confidence: float = 0.0
    is_match: bool = False
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    transferable_skills: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    breakdown: dict[str, Any] = Field(default_factory=dict)


class Gate4eMatchEvaluationReport(BaseModel):
    """Composition: eligibility decisions + read-only match evaluations."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: UUID
    policy_version: int = GATE4E_ELIGIBILITY_POLICY_VERSION
    evaluated_at: datetime | None = None
    eligibility: Gate4eEligibilityReport
    evaluated_job_count: int = 0
    outcomes: list[Gate4eMatchEvaluationOutcome] = Field(default_factory=list)
