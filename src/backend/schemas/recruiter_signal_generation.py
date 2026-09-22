"""CP17 recruiter signal generation contract (offline, deterministic).

CP17 generates ``RecruiterSignal`` records from existing persisted evidence by
evaluating explicit, conservative rules. Nothing in this module discovers,
scores, ranks, contacts, or approves recruiters; it only transforms persisted
evidence into durable signals (via the CP16 foundation) or explicit
suppression reasons.

The generation artifact is deliberately deterministic: every signal identity,
evidence reference, suppression reason, and the run id are derived from the
inputs (candidate, job, recruiter evidence, eligibility, matching) with no
runtime timestamps, so identical inputs produce byte-identical output.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.models.recruiter_signal import RecruiterSignalType

RECRUITER_SIGNAL_GENERATION_VERSION = "cp17.v1"


class RecruiterEvidenceStrength(str, Enum):
    """Deterministic evidence strength categories (never invented)."""

    SUPPORTED = "SUPPORTED"
    INSUFFICIENT = "INSUFFICIENT"
    CONTRADICTED = "CONTRADICTED"


class RecruiterSignalSuppressionReason(str, Enum):
    """Controlled suppression/rejection reasons (no free-form strings)."""

    NO_RECRUITER_EVIDENCE = "NO_RECRUITER_EVIDENCE"
    INSUFFICIENT_RECRUITER_IDENTITY = "INSUFFICIENT_RECRUITER_IDENTITY"
    NO_SUPPORTED_CONTACT = "NO_SUPPORTED_CONTACT"
    JOB_NOT_ELIGIBLE = "JOB_NOT_ELIGIBLE"
    CANDIDATE_NOT_ELIGIBLE = "CANDIDATE_NOT_ELIGIBLE"
    MISSING_PROVENANCE = "MISSING_PROVENANCE"
    UNRESOLVED_SOURCE = "UNRESOLVED_SOURCE"
    DUPLICATE_SIGNAL = "DUPLICATE_SIGNAL"


class FieldProvenance(BaseModel):
    """Field-level provenance: which persisted field backed one value."""

    model_config = ConfigDict(extra="forbid")

    field_name: str
    present: bool
    source: str
    source_reference: str | None = None


class RecruiterEvidence(BaseModel):
    """Internal evidence representation (extracted from persisted data only)."""

    model_config = ConfigDict(extra="forbid")

    recruiter_id: UUID
    candidate_id: UUID
    company_id: UUID | None
    job_id: UUID
    full_name: str | None = None
    role_title: str | None = None
    public_profile_url: str | None = None
    email: str | None = None

    supported_fields: list[str] = Field(default_factory=list)
    contact_methods: list[str] = Field(default_factory=list)

    evidence_strength: RecruiterEvidenceStrength
    identity_supported: bool = False

    # Evidence provenance (never fabricated; NULL stays NULL).
    source: str = ""
    source_reference: str | None = None
    evidence_reference: str = ""

    fields_provenance: dict[str, FieldProvenance] = Field(default_factory=dict)

    def model_dump_deterministic(self) -> dict[str, Any]:
        """Canonical, sorted dump used for byte-identical evaluation artifacts."""
        return {
            "recruiter_id": str(self.recruiter_id),
            "candidate_id": str(self.candidate_id),
            "company_id": str(self.company_id) if self.company_id else None,
            "job_id": str(self.job_id),
            "full_name": self.full_name,
            "role_title": self.role_title,
            "public_profile_url": self.public_profile_url,
            "email": self.email,
            "supported_fields": sorted(self.supported_fields),
            "contact_methods": sorted(self.contact_methods),
            "evidence_strength": self.evidence_strength.value,
            "identity_supported": self.identity_supported,
            "source": self.source,
            "source_reference": self.source_reference,
            "evidence_reference": self.evidence_reference,
        }


class SignalSuppression(BaseModel):
    """Why a rule did not generate a signal for a specific context."""

    model_config = ConfigDict(extra="forbid")

    reason: RecruiterSignalSuppressionReason
    reason_detail: str
    job_id: UUID | None = None
    recruiter_id: UUID | None = None
    rule: str
    eligibility_code: str | None = None


class GeneratedSignal(BaseModel):
    """One deterministic signal outcome for one (job, recruiter, rule)."""

    model_config = ConfigDict(extra="forbid")

    signal_identity: str
    signal_type: RecruiterSignalType
    job_id: UUID
    recruiter_id: UUID | None = None
    evidence_reference: str
    outcome: str  # "created" | "deduplicated"


class RecruiterSignalGenerationResult(BaseModel):
    """Deterministic generation artifact for one candidate."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: UUID
    generation_version: str = RECRUITER_SIGNAL_GENERATION_VERSION
    run_id: str
    policy_version: int
    partial_with_url_policy: str

    eligibility_records_total: int
    eligible_job_count: int
    excluded_job_count: int

    evidence_loaded: list[RecruiterEvidence] = Field(default_factory=list)

    generated: list[GeneratedSignal] = Field(default_factory=list)
    suppressed: list[SignalSuppression] = Field(default_factory=list)
    signal_type_counts: dict[str, int] = Field(default_factory=dict)

    created_count: int = 0
    deduplicated_count: int = 0
    suppressed_count: int = 0

    generated_at: datetime | None = None

    def model_dump_deterministic(self) -> dict[str, Any]:
        """Canonical dump for byte-identical evaluation artifacts.

        ``generated_at`` is intentionally excluded so identical inputs yield
        identical output across runs.
        """
        data = self.model_dump(mode="json")
        data.pop("generated_at", None)
        data["evidence_loaded"] = sorted(
            (e.model_dump_deterministic() for e in self.evidence_loaded),
            key=lambda e: e["evidence_reference"],
        )
        data["generated"] = sorted(
            data["generated"],
            key=lambda g: g["signal_identity"],
        )
        data["suppressed"] = sorted(
            data["suppressed"],
            key=lambda s: (
                s["job_id"] or "",
                s["rule"],
                s["reason"],
                s["recruiter_id"] or "",
            ),
        )
        data["signal_type_counts"] = dict(sorted(data["signal_type_counts"].items()))
        return data
