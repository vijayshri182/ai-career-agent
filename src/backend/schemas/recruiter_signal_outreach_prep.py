"""CP20 recruiter-signal outreach preparation contract.

A durable, deterministic preparation artifact produced for an APPROVED
(``recruiter_signal_review``) outreach-candidate signal. The draft content is
grounded exclusively in verified candidate facts plus verified contact/job
information by the shared deterministic writer; nothing here invents facts,
sends anything, or reaches the network. Every preparation artifact carries the
exact signal/evidence linkage (signal identity, evidence reference, generation
version, approval id) so it can be traced back to the persisted source.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.models.outreach import OutreachChannel

RECRUITER_SIGNAL_OUTREACH_PREP_VERSION = "cp20.v1"


class RecruiterSignalLinkage(BaseModel):
    """Exact signal/evidence version linkage carried by a preparation."""

    model_config = ConfigDict(extra="forbid")

    signal_id: UUID
    signal_identity: str
    signal_type: str
    evidence_reference: str
    generation_version: str | None = None
    signal_status: str
    approval_id: UUID


class RecruiterSignalOutreachPreparation(BaseModel):
    """One deterministic, grounded outreach draft prepared from an approved signal."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: UUID
    signal_id: UUID
    contact_id: UUID
    job_id: UUID
    company_id: UUID | None = None

    channel: OutreachChannel = OutreachChannel.EMAIL
    subject: str
    body: str
    rules_version: str
    fact_sources: list[dict[str, Any]] = Field(default_factory=list)

    prep_version: str = RECRUITER_SIGNAL_OUTREACH_PREP_VERSION
    # Deterministic preparation id (no timestamps), for audit correlation.
    prep_id: str
    linkage: RecruiterSignalLinkage
    generated_at: datetime | None = None

    def model_dump_deterministic(self) -> dict[str, Any]:
        """Canonical dump for byte-identical preparation artifacts.

        ``generated_at`` is intentionally excluded so identical inputs yield
        identical output across runs.
        """
        data = self.model_dump(mode="json")
        data.pop("generated_at", None)
        data["fact_sources"] = sorted(
            data["fact_sources"],
            key=lambda source: (
                str(source.get("kind") or ""),
                str(source.get("ref_id") or ""),
                str(source.get("text") or ""),
            ),
        )
        return data
