"""Application preparation schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.models.application import (
    AnswerStatus,
    ApplicationStatus,
    DocumentType,
    QuestionCategory,
)


class QuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category: QuestionCategory
    question_text: str
    source_hint: str | None


class AnswerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    question_id: UUID
    status: AnswerStatus
    answer_text: str
    fact_sources: list[dict[str, object]]
    created_at: datetime
    updated_at: datetime


class QuestionWithAnswerRead(QuestionRead):
    answer: AnswerRead | None = None


class ApplicationAnswerRead(AnswerRead):
    pass


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    doc_type: DocumentType
    title: str
    version_number: int
    is_generated: bool
    generation_version: str | None
    fact_sources: list[dict[str, object]]
    created_at: datetime
    updated_at: datetime


class ApplicationDocumentRead(DocumentRead):
    content: str


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    job_id: UUID
    resume_id: UUID | None
    status: ApplicationStatus
    match_id: UUID | None
    match_score: float | None
    created_at: datetime
    updated_at: datetime


class ApplicationDetailRead(ApplicationRead):
    questions: list[QuestionWithAnswerRead]
    documents: list[DocumentRead]


class PrepareJobRequest(BaseModel):
    resume_id: UUID | None = None


class GenerateDocumentRequest(BaseModel):
    doc_type: DocumentType = DocumentType.COVER_LETTER
    title: str | None = None


class AnswerUpdateRequest(BaseModel):
    answer_text: str


class AnswerUpdateResponse(BaseModel):
    answer: ApplicationAnswerRead
