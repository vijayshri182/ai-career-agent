"""Raw job extraction model storing the untrusted payload per discovery fetch."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import JSON, Column, DateTime, String, Text
from sqlmodel import Field, Relationship

from backend.db.base import IdModel
from backend.models.job import Job

if TYPE_CHECKING:
    from backend.models.candidate import Candidate
    from backend.models.job_source import JobSource


class RawExtractionStatus(str, Enum):
    PARSED = "parsed"
    IGNORED = "ignored"
    ERROR = "error"


class RawJobExtraction(IdModel, table=True):
    """Immutable-ish record of one fetch from a job source.

    Keeps the raw payload available for audit, re-processing, and debugging of
    the normalization/dedup pipeline. External content is stored verbatim and
    is never trusted; `content_hash` (when present) ties it to the normalized
    `Job` it produced.
    """

    __tablename__ = "raw_job_extractions"

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    source_id: UUID = Field(foreign_key="job_sources.id", nullable=False, index=True)
    job_id: UUID | None = Field(foreign_key="jobs.id", nullable=True, index=True)

    fetch_url: str = Field(sa_column=Column(String(2048), nullable=False))
    fetched_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    status: RawExtractionStatus = Field(default=RawExtractionStatus.PARSED)
    raw_payload: dict[str, object] = Field(
        default_factory=dict, sa_column=Column(JSON, default=dict)
    )
    content_hash: str | None = Field(sa_column=Column(String(64), index=True, nullable=True))
    error_message: str | None = Field(sa_column=Column(Text, nullable=True))

    candidate: "Candidate" = Relationship(back_populates="job_extractions")
    source: "JobSource" = Relationship(back_populates="extractions")
    job: "Job" = Relationship(back_populates="extractions")
