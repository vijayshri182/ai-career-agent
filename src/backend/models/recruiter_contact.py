"""Recruiter / professional contact discovery models.

A ``RecruiterContact`` is the durable, candidate-scoped record of a publicly
available recruiting contact for a target company. Discovery only uses public
evidence (official career/team pages, public directories, voluntarily-public
professional networking pages) and is governed by hard privacy boundaries:

* Only contacts whose affiliation is VERIFIED and scores >= 70 are surfaced
  (``is_suppressed`` and the list service filter hide everything else).
* Guessed personal email addresses are never stored (the ``email`` column only
  ever holds a publicly listed address the source explicitly exposed).
* Every surfaced contact links to its public evidence via ``public_profile_url``
  and a ``ContactSource`` row describing where it came from.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import JSON, Boolean, Column, DateTime, Index, Integer, String, Text
from sqlmodel import Field, Relationship

from backend.db.base import IdModel

MIN_SURFACE_CONFIDENCE = 70

if TYPE_CHECKING:
    from backend.models.candidate import Candidate
    from backend.models.company import Company
    from backend.models.job import Job
    from backend.models.outreach import OutreachMessage


class ContactSourceType(str, Enum):
    """Where public evidence came from."""

    CAREER_PAGE = "career_page"
    TEAM_PAGE = "team_page"
    DIRECTORY = "directory"
    PROFESSIONAL_NETWORK = "professional_network"
    OTHER_PUBLIC = "other_public"


class ContactType(str, Enum):
    """Affiliation trust level of a discovered contact."""

    VERIFIED = "verified"
    GUESSED = "guessed"


class ContactSource(IdModel, table=True):
    __tablename__ = "contact_sources"

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    company_id: UUID | None = Field(foreign_key="companies.id", nullable=True, index=True)

    source_type: ContactSourceType = Field(
        sa_column=Column(String(32), nullable=False, server_default="other_public"),
        default=ContactSourceType.OTHER_PUBLIC,
    )
    url: str = Field(sa_column=Column(Text, nullable=False))
    title: str | None = Field(sa_column=Column(String(255), nullable=True))
    note: str | None = Field(sa_column=Column(Text, nullable=True))
    discovered_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": False},  # type: ignore[call-overload]
    )

    contacts: list["RecruiterContact"] = Relationship(back_populates="source")
    candidate: "Candidate" = Relationship(back_populates="contact_sources")
    company: Optional["Company"] = Relationship(back_populates="contact_sources")


class RecruiterContact(IdModel, table=True):
    __tablename__ = "recruiter_contacts"
    __table_args__ = (
        # Deduplication key: one contact per candidate + public profile URL.
        Index("uq_recruiter_contacts_candidate_profile", "candidate_id", "public_profile_url", unique=True),
    )

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    company_id: UUID = Field(foreign_key="companies.id", nullable=False, index=True)
    job_id: UUID | None = Field(foreign_key="jobs.id", nullable=True, index=True)
    source_id: UUID = Field(foreign_key="contact_sources.id", nullable=False, index=True)

    full_name: str = Field(sa_column=Column(String(255), nullable=False))
    role_title: str = Field(sa_column=Column(String(255), nullable=False))
    # Public profile link that is the evidence for this person (never private).
    public_profile_url: str = Field(sa_column=Column(Text, nullable=False))
    # Only ever set from a publicly listed, source-exposed address.
    email: str | None = Field(sa_column=Column(String(320), nullable=True))

    confidence_score: int = Field(sa_column=Column(Integer, nullable=False, server_default="0"))
    contact_type: ContactType = Field(
        sa_column=Column(String(16), nullable=False, server_default="guessed"),
        default=ContactType.GUESSED,
    )
    # Retention/quality flag: suppressed contacts are never surfaced.
    is_suppressed: bool = Field(
        sa_column=Column(Boolean, nullable=False, server_default="0"), default=False
    )

    verification_details: dict[str, object] = Field(
        default_factory=dict, sa_column=Column(JSON, default=dict)
    )

    candidate: "Candidate" = Relationship(back_populates="recruiter_contacts")
    company: "Company" = Relationship(back_populates="recruiter_contacts")
    job: Optional["Job"] = Relationship(back_populates="recruiter_contacts")
    source: "ContactSource" = Relationship(back_populates="contacts")
    outreach_messages: list["OutreachMessage"] = Relationship(back_populates="contact")
