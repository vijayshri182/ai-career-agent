"""Recruiter signal domain model (data foundation).

A ``RecruiterSignal`` is the durable, candidate-scoped record that a pieces of
public evidence points to recruiter-related facts for a specific job context.
CP16 only establishes the domain model and persistence: nothing in this module
generates, discovers, scores, or contacts recruiters.

Hard boundaries:

* The recruiter person/entity is the existing ``RecruiterContact``; this module
  only ever references it via ``recruiter_contact_id`` (nullable when evidence
  does not identify a specific person).
* ``signal_type`` values are strictly evidence-oriented; no predictive or
  evaluative labels (for example "best recruiter" or "high response") exist.
* A signal never claims a fact that evidence did not provide: unknown identity
  fields stay NULL and ``evidence_json`` only holds what the source actually
  said.
* The lifecycle status defaults to ``DISCOVERED``; ``APPROVED`` can only ever
  be reached through an explicit transition and is never set implicitly at
  creation.
"""

from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Column, String
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, UniqueConstraint

from backend.db.base import IdModel


class RecruiterSignalType(str, Enum):
    """Evidence-oriented classification of one recruiter signal.

    Every value describes only what public evidence showed. None of them
    predict outreach success, response likelihood, or importance.
    """

    # A known recruiting contact is associated with this job/company context.
    RECRUITER_ASSOCIATED = "recruiter_associated"
    # Evidence points to a recruiting role relevant to the posting's company,
    # without identifying a specific person.
    RECRUITER_ROLE_RELEVANT = "recruiter_role_relevant"
    # A public, usable contact element for a known recruiter is available.
    RECRUITER_CONTACT_AVAILABLE = "recruiter_contact_available"
    # The signal is a candidate for future human review as an outreach
    # consideration. Carries no authorization and takes no action.
    RECRUITER_OUTREACH_CANDIDATE = "recruiter_outreach_candidate"


class RecruiterSignalStatus(str, Enum):
    """Lifecycle of a recruiter signal.

    ``APPROVED`` and ``REJECTED`` are explicit human review outcomes; they are
    never assigned implicitly. Human approval remains a separate boundary
    (Approval workflow) that a later phase may build on.
    """

    DISCOVERED = "discovered"
    EVIDENCE_PENDING = "evidence_pending"
    READY_FOR_REVIEW = "ready_for_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class RecruiterSignal(IdModel, table=True):
    """Durable record of one evidence-backed recruiter signal.

    One row per (candidate, deterministic signal identity). Re-recording the
    same evidence is a no-op: the identity is derived from the durable anchors
    (candidate, job, identified recruiter, signal type, producer reference),
    never from mutable display text or timestamps.
    """

    __tablename__ = "recruiter_signals"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id",
            "signal_identity",
            name="uq_recruiter_signals_candidate_identity",
        ),
    )

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    # Signals are scoped to a specific job context for the candidate.
    job_id: UUID = Field(foreign_key="jobs.id", nullable=False, index=True)
    # Identified recruiter when evidence names one; NULL otherwise.
    recruiter_contact_id: UUID | None = Field(
        foreign_key="recruiter_contacts.id", nullable=True, index=True
    )
    # Company context when evidencible; NULL otherwise (never assumed).
    company_id: UUID | None = Field(
        foreign_key="companies.id", nullable=True, index=True
    )

    signal_type: RecruiterSignalType = Field(
        sa_column=Column(
            SAEnum(
                RecruiterSignalType,
                values_callable=lambda e: [m.value for m in e],
                native_enum=False,
            ),
            nullable=False,
            server_default="recruiter_associated",
            index=True,
        ),
        default=RecruiterSignalType.RECRUITER_ASSOCIATED,
    )
    status: RecruiterSignalStatus = Field(
        sa_column=Column(
            SAEnum(
                RecruiterSignalStatus,
                values_callable=lambda e: [m.value for m in e],
                native_enum=False,
            ),
            nullable=False,
            server_default="discovered",
            index=True,
        ),
        default=RecruiterSignalStatus.DISCOVERED,
    )

    # Deterministic deduplication identity (replay -> same row).
    signal_identity: str = Field(sa_column=Column(String(64), nullable=False))
    # Producer of this signal (e.g. an evidence envelope producer id).
    source: str = Field(sa_column=Column(String(128), nullable=False))
    # Reference within the producer's own records (e.g. posting key).
    source_reference: str | None = Field(sa_column=Column(String(255), nullable=True))

    # Lossless evidence: what the source actually said, and where it came from.
    evidence_json: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, default=dict)
    )
    provenance_json: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, default=dict)
    )
