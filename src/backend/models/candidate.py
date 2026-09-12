"""Candidate profile models."""

from datetime import date
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import JSON, Column, Date, Integer, String, Text
from sqlmodel import Field, Relationship

from backend.db.base import IdModel
from backend.db.encrypted_types import EncryptedString

if TYPE_CHECKING:
    from backend.models.application import Application
    from backend.models.approval import Approval
    from backend.models.authentication import AuthProvider
    from backend.models.automation_run import AutomationRun
    from backend.models.browser_session import BrowserSession
    from backend.models.challenge import Challenge
    from backend.models.job import Job
    from backend.models.job_match import JobMatch
    from backend.models.job_source import JobSource
    from backend.models.learning import Feedback, Recommendation
    from backend.models.outreach import OutreachMessage, OutreachRun
    from backend.models.raw_job_extraction import RawJobExtraction
    from backend.models.recruiter_contact import ContactSource, RecruiterContact
    from backend.models.resume import Resume
    from backend.models.secret_reference import SecretReference
    from backend.models.user import User
    from backend.models.workflow_run import WorkflowRun


class ProfileStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DELETED = "deleted"


class WorkMode(str, Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"


class Candidate(IdModel, table=True):
    """Core candidate profile. PII fields are encrypted at the application layer."""

    __tablename__ = "candidates"

    user_id: UUID = Field(foreign_key="users.id", nullable=False, index=True, unique=True)
    full_name: str | None = Field(sa_column=Column(EncryptedString(255), nullable=True))
    email_hash: str | None = Field(sa_column=Column(String(64), index=True, nullable=True))
    email_encrypted: str | None = Field(sa_column=Column(EncryptedString(512), nullable=True))
    phone_encrypted: str | None = Field(sa_column=Column(EncryptedString(64), nullable=True))

    headline: str | None = Field(sa_column=Column(EncryptedString(255), nullable=True))
    summary: str | None = Field(sa_column=Column(EncryptedString(4000), nullable=True))

    current_role: str | None = Field(sa_column=Column(String(255), nullable=True))
    target_role: str | None = Field(sa_column=Column(String(255), nullable=True))
    total_experience_years: int | None = Field(sa_column=Column(Integer, nullable=True))

    current_location_json: str | None = Field(
        sa_column=Column(EncryptedString(1024), nullable=True)
    )
    work_authorization: str | None = Field(sa_column=Column(String(128), nullable=True))
    work_mode_preference: WorkMode | None = Field(sa_column=Column(String(32), nullable=True))
    notice_period_days: int | None = Field(sa_column=Column(Integer, nullable=True))

    expected_compensation_amount: int | None = Field(sa_column=Column(Integer, nullable=True))
    expected_compensation_currency: str | None = Field(sa_column=Column(String(8), nullable=True))
    employment_type: str | None = Field(sa_column=Column(String(64), nullable=True))
    seniority: str | None = Field(sa_column=Column(String(64), nullable=True))

    career_preferences: dict[str, object] = Field(
        default_factory=dict, sa_column=Column(JSON, default=dict)
    )
    status: ProfileStatus = Field(default=ProfileStatus.ACTIVE)

    @property
    def email(self) -> str | None:
        from backend.core.security_service import get_security_service

        return get_security_service().decrypt(self.email_encrypted)

    @property
    def phone(self) -> str | None:
        from backend.core.security_service import get_security_service

        return get_security_service().decrypt(self.phone_encrypted)

    @property
    def current_location(self) -> dict[str, object] | None:
        import json
        from typing import cast

        from backend.core.security_service import get_security_service

        raw = get_security_service().decrypt(self.current_location_json)
        if raw is None:
            return None
        return cast(dict[str, object], json.loads(raw))

    user: "User" = Relationship(back_populates="candidates")
    skills: list["CandidateSkill"] = Relationship(back_populates="candidate")
    experiences: list["Experience"] = Relationship(back_populates="candidate")
    educations: list["Education"] = Relationship(back_populates="candidate")
    certifications: list["Certification"] = Relationship(back_populates="candidate")
    resumes: list["Resume"] = Relationship(back_populates="candidate")
    auth_providers: list["AuthProvider"] = Relationship(back_populates="candidate")
    challenges: list["Challenge"] = Relationship(back_populates="candidate")
    secret_references: list["SecretReference"] = Relationship(back_populates="candidate")
    browser_sessions: list["BrowserSession"] = Relationship(back_populates="candidate")
    workflow_runs: list["WorkflowRun"] = Relationship(back_populates="candidate")
    job_sources: list["JobSource"] = Relationship(back_populates="candidate")
    jobs: list["Job"] = Relationship(back_populates="candidate")
    job_extractions: list["RawJobExtraction"] = Relationship(back_populates="candidate")
    job_matches: list["JobMatch"] = Relationship(back_populates="candidate")
    applications: list["Application"] = Relationship(back_populates="candidate")
    approvals: list["Approval"] = Relationship(back_populates="candidate")
    automation_runs: list["AutomationRun"] = Relationship(back_populates="candidate")
    recruiter_contacts: list["RecruiterContact"] = Relationship(back_populates="candidate")
    contact_sources: list["ContactSource"] = Relationship(back_populates="candidate")
    outreach_messages: list["OutreachMessage"] = Relationship(back_populates="candidate")
    outreach_runs: list["OutreachRun"] = Relationship(back_populates="candidate")
    feedbacks: list["Feedback"] = Relationship(back_populates="candidate")
    recommendations: list["Recommendation"] = Relationship(back_populates="candidate")


class SkillCategory(str, Enum):
    PROGRAMMING = "programming"
    FRAMEWORK = "framework"
    CLOUD = "cloud"
    DEVOPS = "devops"
    DATABASE = "database"
    MESSAGING = "messaging"
    TELECOM = "telecom"
    OSS_BSS = "oss_bss"
    ARCHITECTURE = "architecture"
    AI_GENAI = "ai_genai"
    MANAGEMENT = "management"
    TOOLS = "tools"
    OTHER = "other"


class Proficiency(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class CandidateSkill(IdModel, table=True):
    """Skill associated with a candidate."""

    __tablename__ = "candidate_skills"

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    name: str = Field(sa_column=Column(String(128), nullable=False))
    category: SkillCategory = Field(default=SkillCategory.OTHER)
    proficiency: Proficiency = Field(default=Proficiency.INTERMEDIATE)
    years_experience: int | None = Field(sa_column=Column(Integer, nullable=True))
    last_used_year: int | None = Field(sa_column=Column(Integer, nullable=True))
    is_primary: bool = Field(default=False)

    candidate: Candidate = Relationship(back_populates="skills")


class Experience(IdModel, table=True):
    """Employment or project experience."""

    __tablename__ = "experiences"

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    company_name: str = Field(sa_column=Column(String(255), nullable=False))
    title: str = Field(sa_column=Column(String(255), nullable=False))
    location: str | None = Field(sa_column=Column(String(255), nullable=True))
    start_date: date = Field(sa_column=Column(Date, nullable=False))
    end_date: date | None = Field(sa_column=Column(Date, nullable=True))
    is_current: bool = Field(default=False)
    description: str | None = Field(sa_column=Column(Text, nullable=True))
    responsibilities: list[str] = Field(default_factory=list, sa_column=Column(JSON, default=list))
    achievements: list[str] = Field(default_factory=list, sa_column=Column(JSON, default=list))
    technologies: list[str] = Field(default_factory=list, sa_column=Column(JSON, default=list))
    domain: str | None = Field(sa_column=Column(String(128), nullable=True))
    leadership_responsibilities: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, default=list)
    )
    team_size: int | None = Field(sa_column=Column(Integer, nullable=True))
    display_order: int = Field(default=0)

    candidate: Candidate = Relationship(back_populates="experiences")


class Education(IdModel, table=True):
    """Education background."""

    __tablename__ = "educations"

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    institution: str = Field(sa_column=Column(String(255), nullable=False))
    degree: str = Field(sa_column=Column(String(255), nullable=False))
    field_of_study: str | None = Field(sa_column=Column(String(255), nullable=True))
    start_date: date | None = Field(sa_column=Column(Date, nullable=True))
    end_date: date | None = Field(sa_column=Column(Date, nullable=True))
    grade: str | None = Field(sa_column=Column(String(64), nullable=True))
    description: str | None = Field(sa_column=Column(Text, nullable=True))
    display_order: int = Field(default=0)

    candidate: Candidate = Relationship(back_populates="educations")


class Certification(IdModel, table=True):
    """Professional certifications."""

    __tablename__ = "certifications"

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    name: str = Field(sa_column=Column(String(255), nullable=False))
    issuing_organization: str | None = Field(sa_column=Column(String(255), nullable=True))
    issue_date: date | None = Field(sa_column=Column(Date, nullable=True))
    expiry_date: date | None = Field(sa_column=Column(Date, nullable=True))
    credential_id: str | None = Field(sa_column=Column(String(255), nullable=True))
    credential_url: str | None = Field(sa_column=Column(String(1024), nullable=True))
    display_order: int = Field(default=0)

    candidate: Candidate = Relationship(back_populates="certifications")
