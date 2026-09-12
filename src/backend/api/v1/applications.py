"""Application preparation router (fact-grounded, deterministic materials)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from backend.api.deps import (
    get_application_prep_service,
    get_current_user_id,
    get_owned_candidate,
    handle_domain_error,
)
from backend.models.application import (
    Application,
    ApplicationDocument,
    ApplicationStatus,
    DocumentType,
)
from backend.schemas.application import (
    AnswerUpdateRequest,
    AnswerUpdateResponse,
    ApplicationAnswerRead,
    ApplicationDetailRead,
    ApplicationDocumentRead,
    ApplicationRead,
)
from backend.services.application_prep import ApplicationPrepService

router = APIRouter(prefix="/candidates/{candidate_id}/applications", tags=["applications"])


def _application_read(app: Application) -> ApplicationRead:
    return ApplicationRead.model_validate(app)


@router.post(
    "/jobs/{job_id}/prepare",
    response_model=ApplicationDetailRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def prepare_application(
    candidate_id: UUID,
    job_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ApplicationPrepService = Depends(get_application_prep_service),
    resume_id: UUID | None = Query(default=None),
):
    try:
        app = await service.prepare(candidate_id, user_id, job_id, resume_id=resume_id)
        return await service.get_application_detail(candidate_id, user_id, app.id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get(
    "",
    response_model=list[ApplicationRead],
    dependencies=[Depends(get_owned_candidate)],
)
async def list_applications(
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ApplicationPrepService = Depends(get_application_prep_service),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    try:
        items, _total = await service.list_applications(candidate_id, user_id, limit, offset)
        return [_application_read(app) for app in items]
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get(
    "/{application_id}",
    response_model=ApplicationDetailRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def get_application(
    candidate_id: UUID,
    application_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ApplicationPrepService = Depends(get_application_prep_service),
):
    try:
        return await service.get_application_detail(candidate_id, user_id, application_id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get(
    "/{application_id}/documents",
    response_model=list[ApplicationDocumentRead],
    dependencies=[Depends(get_owned_candidate)],
)
async def list_documents(
    candidate_id: UUID,
    application_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ApplicationPrepService = Depends(get_application_prep_service),
):
    try:
        docs = await service.list_documents(candidate_id, user_id, application_id)
        return [_document_read(doc) for doc in docs]
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post(
    "/{application_id}/documents/generate",
    response_model=ApplicationDocumentRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def generate_document(
    candidate_id: UUID,
    application_id: UUID,
    doc_type: DocumentType = Query(default=DocumentType.COVER_LETTER),
    user_id: UUID = Depends(get_current_user_id),
    service: ApplicationPrepService = Depends(get_application_prep_service),
):
    try:
        doc = await service.generate_document(candidate_id, user_id, application_id, doc_type)
        return _document_read(doc)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get(
    "/{application_id}/documents/{document_id}",
    response_model=ApplicationDocumentRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def get_document(
    candidate_id: UUID,
    application_id: UUID,
    document_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ApplicationPrepService = Depends(get_application_prep_service),
):
    try:
        doc = await service.get_document(candidate_id, user_id, application_id, document_id)
        return _document_read(doc)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.put(
    "/{application_id}/questions/{question_id}/answer",
    response_model=AnswerUpdateResponse,
    dependencies=[Depends(get_owned_candidate)],
)
async def update_answer(
    candidate_id: UUID,
    application_id: UUID,
    question_id: UUID,
    request: AnswerUpdateRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: ApplicationPrepService = Depends(get_application_prep_service),
):
    try:
        answer = await service.update_answer(
            candidate_id, user_id, application_id, question_id, request.answer_text
        )
        return AnswerUpdateResponse(
            answer=ApplicationAnswerRead(
                id=answer.id,
                question_id=answer.question_id,
                status=answer.status,
                answer_text=answer.answer_text,
                fact_sources=answer.fact_sources,
                created_at=answer.created_at,
                updated_at=answer.updated_at,
            )
        )
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post(
    "/{application_id}/status",
    response_model=ApplicationRead,
    dependencies=[Depends(get_owned_candidate)],
)
async def update_status(
    candidate_id: UUID,
    application_id: UUID,
    status_value: ApplicationStatus = Query(alias="status"),
    user_id: UUID = Depends(get_current_user_id),
    service: ApplicationPrepService = Depends(get_application_prep_service),
):
    try:
        app = await service.update_status(candidate_id, user_id, application_id, status_value)
        return _application_read(app)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


def _document_read(doc: ApplicationDocument) -> ApplicationDocumentRead:
    return ApplicationDocumentRead(
        id=doc.id,
        application_id=doc.application_id,
        doc_type=doc.doc_type,
        title=doc.title,
        version_number=doc.version_number,
        is_generated=doc.is_generated,
        generation_version=doc.generation_version,
        fact_sources=doc.fact_sources,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        content=doc.content,
    )
