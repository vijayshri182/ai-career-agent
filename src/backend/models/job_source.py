"""Job source models describing where job postings are discovered."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import JSON, Column, DateTime, String, Text
from sqlmodel import Field, Relationship, UniqueConstraint

from backend.db.base import IdModel

if TYPE_CHECKING:
    from backend.models.candidate import Candidate
    from backend.models.job import Job
    from backend.models.raw_job_extraction import RawJobExtraction


class JobSourceType(str, Enum):
    """High-level category of a job feed."""

    COMPANY_CAREERS = "company_careers"
    ATS = "ats"
    API = "api"
    JOB_BOARD = "job_board"
    RSS = "rss"


class JobSource(IdModel, table=True):
    """A permitted, candidate-owned source of job postings.

    Sources are per-candidate so each user controls their own allow-list of
    legitimate feeds. Crawling a source only happens when the operator confirms
    the site permits automation (`terms_allow_automation`) and the source is
    enabled. External content is always treated as untrusted data.
    """

    __tablename__ = "job_sources"
    __table_args__ = (
        UniqueConstraint("candidate_id", "name", name="uq_job_sources_candidate_name"),
    )

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    name: str = Field(sa_column=Column(String(128), nullable=False))
    source_type: JobSourceType = Field(default=JobSourceType.JOB_BOARD)
    base_url: str = Field(sa_column=Column(String(1024), nullable=False))
    terms_allow_automation: bool = Field(default=False)
    is_enabled: bool = Field(default=False)
    crawl_config: dict[str, object] = Field(
        default_factory=dict, sa_column=Column(JSON, default=dict)
    )
    last_error: str | None = Field(sa_column=Column(Text, nullable=True))
    last_run_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    last_success_at: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    candidate: "Candidate" = Relationship(back_populates="job_sources")
    jobs: list["Job"] = Relationship(
        back_populates="source", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    extractions: list["RawJobExtraction"] = Relationship(
        back_populates="source",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
