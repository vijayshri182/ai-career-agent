"""Recruiter / professional contact discovery router.

Candidate-scoped (project convention): routes depend on ``get_owned_candidate``
and the service re-checks ownership. Discovery only queries public evidence;
guessed emails are never stored and only VERIFIED contacts with confidence >= 70
are surfaced by the list endpoint.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from backend.api.deps import (
    get_current_user_id,
    get_owned_candidate,
    get_recruiter_discovery_service,
    handle_domain_error,
)
from backend.models.recruiter_contact import RecruiterContact
from backend.schemas.recruiter_contact import (
    DiscoverContactsResponse,
    RecruiterContactListResponse,
    RecruiterContactRead,
)
from backend.services.recruiter_discovery import RecruiterDiscoveryService

router = APIRouter(prefix="/candidates/{candidate_id}", tags=["recruiter-contacts"])


def _contact_read(contact: RecruiterContact) -> RecruiterContactRead:
    return RecruiterContactRead.model_validate(contact)


@router.post(
    "/jobs/{job_id}/discover-contacts",
    response_model=DiscoverContactsResponse,
    dependencies=[Depends(get_owned_candidate)],
)
async def discover_contacts(
    candidate_id: UUID,
    job_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: RecruiterDiscoveryService = Depends(get_recruiter_discovery_service),
):
    try:
        summary = await service.discover_for_job(job_id)
        return DiscoverContactsResponse(
            found=summary.found,
            created=summary.created,
            existing_skipped=summary.existing_skipped,
            hidden=summary.hidden,
            contacts=[_contact_read(c) for c in summary.contacts],
        )
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get(
    "/recruiter-contacts",
    response_model=RecruiterContactListResponse,
    dependencies=[Depends(get_owned_candidate)],
)
async def list_contacts(
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: RecruiterDiscoveryService = Depends(get_recruiter_discovery_service),
    company_id: UUID | None = Query(default=None),
    job_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    try:
        items, total = await service.list_contacts(
            company_id=company_id, job_id=job_id, limit=limit, offset=offset
        )
        return RecruiterContactListResponse(
            items=[_contact_read(c) for c in items], total=total
        )
    except Exception as exc:
        raise handle_domain_error(exc) from exc
