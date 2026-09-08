"""Resume management models."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlmodel import Field, Relationship

from backend.db.base import IdModel

if TYPE_CHECKING:
    from backend.models.candidate import Candidate


class ResumeStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DELETED = "deleted"


class ResumeType(str, Enum):
    GENERAL = "general"
    TECHNICAL_MANAGER = "technical_manager"
    ENGINEERING_MANAGER = "engineering_manager"
    AI_GENAI = "ai_genai"
    SOLUTION_ARCHITECT = "solution_architect"
    CUSTOM = "custom"


class Resume(IdModel, table=True):
    """Container for a named resume with multiple versions."""

    __tablename__ = "resumes"

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    name: str = Field(sa_column=Column(String(255), nullable=False))
    resume_type: ResumeType = Field(default=ResumeType.GENERAL)
    target_role: str | None = Field(sa_column=Column(String(255), nullable=True))
    is_default: bool = Field(default=False)
    status: ResumeStatus = Field(default=ResumeStatus.ACTIVE)
    active_version_id: UUID | None = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("resume_versions.id", use_alter=True),
            nullable=True,
        )
    )

    candidate: "Candidate" = Relationship(back_populates="resumes")
    versions: list["ResumeVersion"] = Relationship(
        back_populates="resume",
        sa_relationship_kwargs={"foreign_keys": "ResumeVersion.resume_id"},
    )

    @property
    def active_version(self) -> "ResumeVersion | None":
        if self.active_version_id is None:
            return None
        for version in self.versions:
            if str(version.id) == str(self.active_version_id):
                return version
        return None


class ResumeVersion(IdModel, table=True):
    """A specific uploaded version of a resume."""

    __tablename__ = "resume_versions"

    resume_id: UUID = Field(foreign_key="resumes.id", nullable=False, index=True)
    version_number: int = Field(sa_column=Column(Integer, nullable=False))
    original_filename: str = Field(sa_column=Column(String(512), nullable=False))
    storage_backend: str = Field(sa_column=Column(String(64), nullable=False))
    storage_path: str = Field(sa_column=Column(Text, nullable=False))
    content_type: str = Field(sa_column=Column(String(128), nullable=False))
    size_bytes: int = Field(sa_column=Column(Integer, nullable=False))
    is_source_version: bool = Field(default=True)
    parsed_status: str = Field(default="pending")  # pending | parsed | failed
    parsed_at: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    resume: Resume = Relationship(
        back_populates="versions",
        sa_relationship_kwargs={"foreign_keys": "ResumeVersion.resume_id"},
    )


class ParsedResume(IdModel, table=True):
    """Extraction output from a resume parser. Requires user confirmation before applying."""

    __tablename__ = "parsed_resumes"

    resume_version_id: UUID = Field(
        foreign_key="resume_versions.id", nullable=False, unique=True
    )
    raw_text: str | None = Field(sa_column=Column(Text, nullable=True))
    extracted_data: dict[str, object] = Field(
        default_factory=dict, sa_column=Column(JSON, default=dict)
    )
    status: str = Field(default="pending")  # pending | reviewed | applied | rejected
    confidence_score: int | None = Field(sa_column=Column(Integer, nullable=True))
    reviewed_at: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    applied_at: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    resume_version: ResumeVersion = Relationship()
