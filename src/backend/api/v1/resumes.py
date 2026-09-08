"""Resume router."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status

from backend.api.deps import get_current_user_id, get_resume_service, handle_domain_error
from backend.schemas.resume import (
    ApplyParsedResumeRequest,
    ParsedResumeRead,
    ResumeCreate,
    ResumeRead,
    ResumeUpdate,
    ResumeVersionRead,
)
from backend.services.resume import ResumeService

router = APIRouter(prefix="/candidates/{candidate_id}/resumes", tags=["resumes"])


@router.get("", response_model=list[ResumeRead])
async def list_resumes(
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ResumeService = Depends(get_resume_service),
):
    return await service.list_resumes(candidate_id)


@router.post("", response_model=ResumeRead, status_code=status.HTTP_201_CREATED)
async def create_resume(
    candidate_id: UUID,
    data: ResumeCreate,
    user_id: UUID = Depends(get_current_user_id),
    service: ResumeService = Depends(get_resume_service),
):
    try:
        resume = await service.create_resume(candidate_id, user_id, data)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return resume


@router.put("/{resume_id}", response_model=ResumeRead)
async def update_resume(
    candidate_id: UUID,
    resume_id: UUID,
    data: ResumeUpdate,
    user_id: UUID = Depends(get_current_user_id),
    service: ResumeService = Depends(get_resume_service),
):
    try:
        resume = await service.update_resume(candidate_id, user_id, resume_id, data)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return resume


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(
    candidate_id: UUID,
    resume_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ResumeService = Depends(get_resume_service),
):
    try:
        await service.delete_resume(candidate_id, user_id, resume_id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return None


@router.post("/{resume_id}/upload", response_model=ResumeVersionRead, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    candidate_id: UUID,
    resume_id: UUID,
    file: UploadFile = File(...),
    user_id: UUID = Depends(get_current_user_id),
    service: ResumeService = Depends(get_resume_service),
):
    try:
        version = await service.upload_resume(candidate_id, user_id, resume_id, file)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return version


@router.post("/upload", response_model=ResumeVersionRead, status_code=status.HTTP_201_CREATED)
async def upload_new_resume(
    candidate_id: UUID,
    file: UploadFile = File(...),
    user_id: UUID = Depends(get_current_user_id),
    service: ResumeService = Depends(get_resume_service),
):
    try:
        version = await service.upload_resume(candidate_id, user_id, None, file)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return version


@router.post("/{resume_id}/parse", response_model=ParsedResumeRead)
async def parse_resume(
    candidate_id: UUID,
    resume_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ResumeService = Depends(get_resume_service),
):
    try:
        parsed = await service.parse_resume(candidate_id, user_id, resume_id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return parsed


@router.get("/{resume_id}/parse", response_model=ParsedResumeRead)
async def get_parsed_resume(
    candidate_id: UUID,
    resume_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ResumeService = Depends(get_resume_service),
):
    try:
        parsed = await service.get_parsed_resume(candidate_id, resume_id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return parsed


@router.post("/{resume_id}/apply-parsed", response_model=ParsedResumeRead)
async def apply_parsed_resume(
    candidate_id: UUID,
    resume_id: UUID,
    request: ApplyParsedResumeRequest = Depends(),
    user_id: UUID = Depends(get_current_user_id),
    service: ResumeService = Depends(get_resume_service),
):
    try:
        if not request.confirm:
            from backend.core.exceptions import ValidationError

            raise ValidationError("Confirmation required to apply parsed data")
        parsed = await service.apply_parsed_resume(candidate_id, user_id, resume_id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return parsed
