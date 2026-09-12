"""Application preparation models.

An ``Application`` is preparation work for one (candidate, job) pair. It records
the selected resume, the screening questions extracted from the job, the answers
generated strictly from profile facts (flagged when they need human input), and
versioned generated documents (cover letter, tailored resume, answer sheet).

Nothing here invents facts: answers and documents are only assembled from profile
data plus the deterministic match output.
"""

from enum import Enum
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import JSON, Column, ForeignKey, String, Text, Uuid
from sqlmodel import Field, Relationship

from backend.db.base import IdModel
from backend.db.encrypted_types import EncryptedString

if TYPE_CHECKING:
    from backend.models.candidate import Candidate
    from backend.models.job import Job
    from backend.models.resume import Resume


class ApplicationStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    SUBMITTED = "submitted"
    WITHDRAWN = "withdrawn"


class QuestionCategory(str, Enum):
    EXPERIENCE = "experience"
    WORK_AUTHORIZATION = "work_authorization"
    CLEARANCE = "clearance"
    COMPENSATION = "compensation"
    LOCATION = "location"
    AVAILABILITY = "availability"
    MOTIVATION = "motivation"
    TECHNICAL = "technical"
    OTHER = "other"


class AnswerStatus(str, Enum):
    AUTO = "auto"
    REQUIRES_REVIEW = "requires_review"
    MANUAL = "manual"


class DocumentType(str, Enum):
    COVER_LETTER = "cover_letter"
    TAILORED_RESUME = "tailored_resume"
    ANSWERS_SHEET = "answers_sheet"
    OTHER = "other"


class Application(IdModel, table=True):
    __tablename__ = "applications"

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    job_id: UUID = Field(foreign_key="jobs.id", nullable=False, index=True)
    resume_id: UUID | None = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("resumes.id"),
            nullable=True,
        )
    )
    status: ApplicationStatus = Field(default=ApplicationStatus.DRAFT)
    match_id: UUID | None = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("job_matches.id"), nullable=True)
    )
    match_score: float | None = Field(default=None)

    candidate: "Candidate" = Relationship(back_populates="applications")
    job: "Job" = Relationship(back_populates="applications")
    resume: Optional["Resume"] = Relationship(back_populates="applications")
    questions: list["ApplicationQuestion"] = Relationship(
        back_populates="application", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    answers: list["ApplicationAnswer"] = Relationship(
        back_populates="application", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    documents: list["ApplicationDocument"] = Relationship(
        back_populates="application", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


class ApplicationQuestion(IdModel, table=True):
    __tablename__ = "application_questions"

    application_id: UUID = Field(
        foreign_key="applications.id", nullable=False, index=True
    )
    category: QuestionCategory = Field(default=QuestionCategory.OTHER)
    question_text: str = Field(sa_column=Column(Text, nullable=False))
    source_hint: str | None = Field(sa_column=Column(String(128), nullable=True))

    application: Application = Relationship(back_populates="questions")
    answer: Optional["ApplicationAnswer"] = Relationship(
        back_populates="question",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "uselist": False},
    )


class ApplicationAnswer(IdModel, table=True):
    __tablename__ = "application_answers"

    application_id: UUID = Field(
        foreign_key="applications.id", nullable=False, index=True
    )
    question_id: UUID = Field(
        foreign_key="application_questions.id", nullable=False, unique=True
    )
    status: AnswerStatus = Field(default=AnswerStatus.REQUIRES_REVIEW)
    answer_text: str = Field(sa_column=Column(Text, nullable=False, default=""))
    fact_sources: list[dict[str, object]] = Field(
        default_factory=list, sa_column=Column(JSON, default=list)
    )

    application: Application = Relationship(
        back_populates="answers",
        sa_relationship_kwargs={"foreign_keys": "ApplicationAnswer.application_id"},
    )
    question: "ApplicationQuestion" = Relationship(back_populates="answer")


class ApplicationDocument(IdModel, table=True):
    __tablename__ = "application_documents"

    application_id: UUID = Field(
        foreign_key="applications.id", nullable=False, index=True
    )
    doc_type: DocumentType = Field(default=DocumentType.OTHER)
    title: str = Field(sa_column=Column(String(255), nullable=False))
    version_number: int = Field(default=1)
    is_generated: bool = Field(default=True)
    content: str = Field(
        sa_column=Column(EncryptedString(65535), nullable=False, default="")
    )
    generation_version: str | None = Field(sa_column=Column(String(64), nullable=True))
    fact_sources: list[dict[str, object]] = Field(
        default_factory=list, sa_column=Column(JSON, default=list)
    )

    application: Application = Relationship(back_populates="documents")
