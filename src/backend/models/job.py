"""Job posting model with deduplication keys and freshness tracking."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Column, DateTime, String, Text
from sqlmodel import Field, Relationship, UniqueConstraint

from backend.db.base import IdModel

if TYPE_CHECKING:
    from backend.models.candidate import Candidate
    from backend.models.company import Company
    from backend.models.job_match import JobMatch
    from backend.models.job_source import JobSource
    from backend.models.raw_job_extraction import RawJobExtraction


class JobStatus(str, Enum):
    """Lifecycle of a job posting."""

    DISCOVERED = "discovered"
    VERIFIED = "verified"
    EXPIRED = "expired"
    REJECTED = "rejected"


class Job(IdModel, table=True):
    """A single normalized job posting, scoped to one candidate.

    Deduplication is enforced at three complementary levels, each per-candidate
    (two candidates legitimately follow the same public posting):
    * unique `(candidate_id, url)` — the most specific key;
    * unique `(candidate_id, company_id, external_id)` — the employer's own
      requisition key;
    * indexed `content_hash` — a normalized title/location/description
      fingerprint used to merge near-identical postings across URLs.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("candidate_id", "url", name="uq_jobs_candidate_url"),
        UniqueConstraint(
            "candidate_id", "company_id", "external_id", name="uq_jobs_candidate_company_external"
        ),
    )

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    company_id: UUID = Field(foreign_key="companies.id", nullable=False, index=True)
    source_id: UUID = Field(foreign_key="job_sources.id", nullable=False, index=True)

    external_id: str | None = Field(sa_column=Column(String(255), nullable=True))
    url: str = Field(sa_column=Column(String(2048), nullable=False))
    title: str = Field(sa_column=Column(String(512), nullable=False))
    location: str | None = Field(sa_column=Column(String(255), nullable=True))
    description: str | None = Field(sa_column=Column(Text, nullable=True))
    content_hash: str = Field(sa_column=Column(String(64), nullable=False, index=True))

    status: JobStatus = Field(default=JobStatus.DISCOVERED, index=True)
    posted_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    closing_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    first_seen_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    last_seen_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))

    candidate: "Candidate" = Relationship(back_populates="jobs")
    company: "Company" = Relationship(back_populates="jobs")
    source: "JobSource" = Relationship(back_populates="jobs")
    matches: list["JobMatch"] = Relationship(back_populates="job")
    extractions: list["RawJobExtraction"] = Relationship(
        back_populates="job", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
