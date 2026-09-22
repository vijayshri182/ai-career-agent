"""Versioned Gate 4E evidence-envelope schemas and ingestion result types.

These schemas model the CP12 Option-B versioned handoff envelope. Records are
typed field-for-field against the Gate 4E CP10 official-postings artifact and
are intentionally permissive (`extra="ignore"`); every record is also preserved
verbatim in the ACA-owned ingestion store so unknown producer fields are never
dropped silently.
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.models.gate4e_ingestion import Gate4eProcessingStatus

GATE4E_SCHEMA_VERSION = 1
SUPPORTED_GATE4E_SCHEMA_VERSIONS = frozenset({GATE4E_SCHEMA_VERSION})


class Gate4eVerificationStatus(str, Enum):
    """Producer verification domain (Gate 4E), preserved for audit."""

    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    UNRESOLVED = "UNRESOLVED"


class Gate4eIngressRecord(BaseModel):
    """One per-alert Gate 4E record (CP10Row shape)."""

    model_config = ConfigDict(extra="ignore")

    index: int | None = None
    job_title: str | None = None
    company_name: str | None = None
    job_location: str | None = None
    original_job_url: str | None = None
    gmail_message_id: str | None = None
    official_domain: str | None = None
    official_job_url: str | None = None
    official_job_id: str | None = None
    verification_status: Gate4eVerificationStatus | None = None
    verification_reason: str | None = None
    title_correspondence: bool | None = None
    company_correspondence: bool | None = None
    description: str | None = None
    skills: list[str] = Field(default_factory=list)
    seniority: str | None = None
    years: str | None = None
    work_mode: str | None = None
    compensation: str | None = None
    provenance: dict[str, str] = Field(default_factory=dict)
    evidence_urls: list[str] = Field(default_factory=list)
    enrichment_covered: list[str] = Field(default_factory=list)
    enrichment_missing: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class Gate4eIngressEnvelope(BaseModel):
    """Versioned handoff envelope; the record rows are the raw producer rows."""

    model_config = ConfigDict(extra="ignore")

    schema_version: int | None = None
    producer_id: str | None = None
    producer_version: str | None = None
    generated_at: str | None = None
    labels: list[str] = Field(default_factory=list)
    alerts_evaluated: int | None = None
    rows: list[dict[str, Any]] = Field(default_factory=list)


class Gate4eIngestionOutcome(BaseModel):
    """Deterministic disposition of one ingested record."""

    alert_index: int | None = None
    verification_status: Gate4eVerificationStatus | None = None
    processing_status: Gate4eProcessingStatus
    ingestion_identity: str | None = None
    posting_key: str | None = None
    job_id: UUID | None = None
    reason: str | None = None
    duplicate: bool = False
    job_created: bool = False


class Gate4eIngestionResult(BaseModel):
    """Deterministic result of an envelope ingestion run."""

    candidate_id: UUID
    schema_version: int | None = None
    producer_id: str | None = None
    producer_version: str | None = None
    generated_at: str | None = None
    rejected: bool = False
    envelope_reason: str | None = None
    total_records: int = 0
    accepted_verified: int = 0
    accepted_partial: int = 0
    quarantined_partial_no_url: int = 0
    quarantined_unresolved: int = 0
    rejected_invalid: int = 0
    duplicates: int = 0
    jobs_created: int = 0
    outcomes: list[Gate4eIngestionOutcome] = Field(default_factory=list)
