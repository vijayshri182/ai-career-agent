"""Certifications router."""

from uuid import UUID

from fastapi import APIRouter, Depends, status

from backend.api.deps import (
    get_certification_service,
    get_current_user_id,
    handle_domain_error,
)
from backend.schemas.certification import (
    CertificationCreate,
    CertificationRead,
    CertificationUpdate,
)
from backend.services.certification import CertificationService

router = APIRouter(prefix="/candidates/{candidate_id}/certifications", tags=["certifications"])


@router.get("", response_model=list[CertificationRead])
async def list_certifications(
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: CertificationService = Depends(get_certification_service),
):
    return await service.list(candidate_id)


@router.post("", response_model=CertificationRead, status_code=status.HTTP_201_CREATED)
async def add_certification(
    candidate_id: UUID,
    data: CertificationCreate,
    user_id: UUID = Depends(get_current_user_id),
    service: CertificationService = Depends(get_certification_service),
):
    try:
        cert = await service.add(candidate_id, user_id, data)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return cert


@router.put("/{certification_id}", response_model=CertificationRead)
async def update_certification(
    candidate_id: UUID,
    certification_id: UUID,
    data: CertificationUpdate,
    user_id: UUID = Depends(get_current_user_id),
    service: CertificationService = Depends(get_certification_service),
):
    try:
        cert = await service.update(candidate_id, user_id, certification_id, data)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return cert


@router.delete("/{certification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_certification(
    candidate_id: UUID,
    certification_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: CertificationService = Depends(get_certification_service),
):
    try:
        await service.delete(candidate_id, user_id, certification_id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return None
