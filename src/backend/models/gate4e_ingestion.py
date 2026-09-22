"""ACA-owned ingestion and quarantine records for the Gate 4E evidence envelope.

One row per ingested Gate 4E alert (identity A). Re-ingesting identical
evidence is a no-op via the deterministic `ingestion_identity`; distinct alerts
that reference the same posting stay separate rows that can share one ACA `Job`
(identity C). The row is lossless: the exact producer record, provenance, and
evidence URLs are retained verbatim in JSON columns and never fabricated.
"""

from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Column, Integer, String, Text
from sqlmodel import Field, UniqueConstraint

from backend.db.base import IdModel


class Gate4eProcessingStatus(str, Enum):
    """ACA-owned disposition for one ingested Gate 4E record."""

    ACCEPTED_VERIFIED = "ACCEPTED_VERIFIED"
    ACCEPTED_PARTIAL = "ACCEPTED_PARTIAL"
    QUARANTINED_PARTIAL_NO_URL = "QUARANTINED_PARTIAL_NO_URL"
    QUARANTINED_UNRESOLVED = "QUARANTINED_UNRESOLVED"
    REJECTED_INVALID = "REJECTED_INVALID"


class Gate4eIngestion(IdModel, table=True):
    """ACA-owned record of one Gate 4E alert, incl. quarantine evidence."""

    __tablename__ = "gate4e_ingestion_records"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id",
            "ingestion_identity",
            name="uq_gate4e_ingestion_candidate_identity",
        ),
    )

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    schema_version: int = Field(sa_column=Column(Integer, nullable=False))
    producer_id: str = Field(sa_column=Column(String(128), nullable=False))
    producer_version: str = Field(sa_column=Column(String(32), nullable=False))

    # Deterministic identity of the producer record (replay -> no-op).
    ingestion_identity: str = Field(sa_column=Column(String(64), nullable=False))

    processing_status: Gate4eProcessingStatus = Field(
        default=Gate4eProcessingStatus.REJECTED_INVALID,
        sa_column=Column(String(32), nullable=False, index=True),
    )
    verification_status: str | None = Field(sa_column=Column(String(16), nullable=True))

    # Identity A (alert/event).
    alert_index: int | None = Field(sa_column=Column(Integer, nullable=True))
    gmail_message_id: str | None = Field(sa_column=Column(String(128), nullable=True))

    # Identity B (posting-level grouping hint).
    posting_key: str | None = Field(sa_column=Column(String(255), nullable=True, index=True))

    # Content.
    company_name: str | None = Field(sa_column=Column(String(255), nullable=True))
    official_domain: str | None = Field(sa_column=Column(String(255), nullable=True))
    job_title: str | None = Field(sa_column=Column(String(512), nullable=True))
    job_location: str | None = Field(sa_column=Column(String(255), nullable=True))
    description: str | None = Field(sa_column=Column(Text, nullable=True))

    # Evidence (never fabricated; official URL is the only Job-eligible value).
    official_job_url: str | None = Field(sa_column=Column(String(2048), nullable=True))
    official_job_id: str | None = Field(sa_column=Column(String(255), nullable=True))
    original_job_url: str | None = Field(sa_column=Column(String(2048), nullable=True))
    content_hash: str | None = Field(sa_column=Column(String(64), nullable=True, index=True))

    # Link to identity C when a normalized ACA Job exists.
    job_id: UUID | None = Field(foreign_key="jobs.id", nullable=True, index=True)

    reason: str | None = Field(sa_column=Column(Text, nullable=True))

    # Lossless producer evidence.
    payload_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, default=dict))
    provenance_json: dict[str, str] = Field(
        default_factory=dict, sa_column=Column(JSON, default=dict)
    )
    evidence_urls_json: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, default=list)
    )
    enrichment_json: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, default=dict)
    )
