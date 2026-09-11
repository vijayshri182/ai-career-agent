"""Authentication & Challenge Management router.

Safe, candidate-scoped endpoints for providers, auth state, challenges,
human-in-the-loop workflows, browser sessions, and secret *references*. No
endpoint accepts or returns raw passwords, OTPs, cookies, or tokens.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status

from backend.api.deps import get_authentication_service, handle_domain_error
from backend.models.challenge import ChallengeStatus
from backend.schemas.authentication import (
    AuthOverview,
    AuthStateReport,
    ChallengeSummaryRead,
    ProviderCreate,
    ProviderRead,
    ProviderStateRead,
    ProviderUpdate,
)
from backend.schemas.browser_session import BrowserSessionCreate, BrowserSessionRead
from backend.schemas.challenge import (
    ChallengeCancelInput,
    ChallengeCompleteInput,
    ChallengeRead,
)
from backend.schemas.secret_reference import (
    SecretReferenceRead,
    SecretReferenceRegister,
    SecretReferenceResolveRead,
)
from backend.schemas.workflow import WorkflowResumeInput, WorkflowRunRead
from backend.services.authentication import AuthenticationService

router = APIRouter(prefix="/candidates/{candidate_id}/auth", tags=["authentication"])


@router.get("/overview", response_model=AuthOverview)
async def auth_overview(
    candidate_id: UUID,  # noqa: ARG001
    service: AuthenticationService = Depends(get_authentication_service),
):
    try:
        return await service.overview()
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get("/providers", response_model=list[ProviderRead])
async def list_providers(
    candidate_id: UUID,  # noqa: ARG001
    service: AuthenticationService = Depends(get_authentication_service),
):
    try:
        return await service.providers.list()
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post("/providers", response_model=ProviderRead, status_code=status.HTTP_201_CREATED)
async def create_provider(
    candidate_id: UUID,  # noqa: ARG001
    data: ProviderCreate,
    service: AuthenticationService = Depends(get_authentication_service),
):
    try:
        return await service.providers.create(data)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get("/providers/{provider_id}", response_model=ProviderRead)
async def get_provider(
    provider_id: UUID,
    candidate_id: UUID,  # noqa: ARG001
    service: AuthenticationService = Depends(get_authentication_service),
):
    try:
        return await service.providers.get(provider_id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.put("/providers/{provider_id}", response_model=ProviderRead)
async def update_provider(
    provider_id: UUID,
    candidate_id: UUID,  # noqa: ARG001
    data: ProviderUpdate,
    service: AuthenticationService = Depends(get_authentication_service),
):
    try:
        return await service.providers.update(provider_id, data)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: UUID,
    candidate_id: UUID,  # noqa: ARG001
    service: AuthenticationService = Depends(get_authentication_service),
):
    try:
        await service.providers.delete(provider_id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    return None


@router.get("/providers/{provider_id}/state", response_model=ProviderStateRead)
async def get_provider_state(
    provider_id: UUID,
    candidate_id: UUID,  # noqa: ARG001
    service: AuthenticationService = Depends(get_authentication_service),
):
    try:
        return await service.providers.get_state(provider_id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post("/providers/{provider_id}/state", response_model=ProviderStateRead)
async def report_state(
    provider_id: UUID,
    candidate_id: UUID,  # noqa: ARG001
    data: AuthStateReport,
    service: AuthenticationService = Depends(get_authentication_service),
):
    try:
        return await service.observe_state(
            provider_id,
            data.status,
            metadata=data.metadata,
            session_reference=data.session_reference,
        )
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get("/challenges", response_model=list[ChallengeRead])
async def list_challenges(
    candidate_id: UUID,  # noqa: ARG001
    open_only: bool = False,
    challenge_status: ChallengeStatus | None = None,
    service: AuthenticationService = Depends(get_authentication_service),
):
    try:
        return await service.challenges.list(status=challenge_status, open_only=open_only)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get("/challenges/outstanding", response_model=list[ChallengeSummaryRead])
async def outstanding_challenges(
    candidate_id: UUID,  # noqa: ARG001
    service: AuthenticationService = Depends(get_authentication_service),
):
    """List challenges that still need human action."""
    try:
        challenges = await service.challenges.list(open_only=True)
        return [
            ChallengeSummaryRead(
                id=c.id,
                provider_id=c.provider_id,
                challenge_type=c.challenge_type.value,
                status=c.status.value,
                severity=c.severity.value,
                human_required=c.human_required,
                detected_at=c.detected_at,
                expires_at=c.expires_at,
            )
            for c in challenges
        ]
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get("/challenges/{challenge_id}", response_model=ChallengeRead)
async def get_challenge(
    challenge_id: UUID,
    candidate_id: UUID,  # noqa: ARG001
    service: AuthenticationService = Depends(get_authentication_service),
):
    try:
        return await service.challenges.get(challenge_id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post("/challenges/{challenge_id}/acknowledge", response_model=ChallengeRead)
async def acknowledge_challenge(
    challenge_id: UUID,
    candidate_id: UUID,  # noqa: ARG001
    service: AuthenticationService = Depends(get_authentication_service),
):
    try:
        challenge = await service.challenges.get(challenge_id)
        return await service.challenges.acknowledge(challenge)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post("/challenges/{challenge_id}/complete", response_model=ChallengeRead)
async def complete_challenge(
    challenge_id: UUID,
    candidate_id: UUID,  # noqa: ARG001
    data: ChallengeCompleteInput,
    service: AuthenticationService = Depends(get_authentication_service),
):
    try:
        challenge = await service.challenges.get(challenge_id)
        return await service.challenges.complete(
            challenge, resolution_method=data.resolution_method, notes=data.notes
        )
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post("/challenges/{challenge_id}/cancel", response_model=ChallengeRead)
async def cancel_challenge(
    challenge_id: UUID,
    candidate_id: UUID,  # noqa: ARG001
    data: ChallengeCancelInput | None = None,
    service: AuthenticationService = Depends(get_authentication_service),
):
    try:
        challenge = await service.challenges.get(challenge_id)
        reason = data.reason if data else None
        return await service.challenges.cancel(challenge, reason=reason)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post("/workflows/{workflow_id}/resume", response_model=WorkflowRunRead)
async def resume_workflow(
    workflow_id: UUID,
    candidate_id: UUID,  # noqa: ARG001
    data: WorkflowResumeInput | None = None,
    service: AuthenticationService = Depends(get_authentication_service),
):
    try:
        run = await service.workflows.get_or_404(workflow_id)
        token = data.resume_token if data else None
        return await service.workflows.resume(run, token)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post("/browser-sessions", response_model=BrowserSessionRead, status_code=status.HTTP_201_CREATED)
async def create_browser_session(
    candidate_id: UUID,  # noqa: ARG001
    data: BrowserSessionCreate,
    service: AuthenticationService = Depends(get_authentication_service),
):
    try:
        return await service.browser_sessions.create(
            data.provider_id,
            storage_reference=data.storage_reference,
            external_session_id=data.external_session_id,
        )
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get("/browser-sessions", response_model=list[BrowserSessionRead])
async def list_browser_sessions(
    candidate_id: UUID,  # noqa: ARG001
    provider_id: UUID | None = None,
    service: AuthenticationService = Depends(get_authentication_service),
):
    try:
        return await service.browser_sessions.list(provider_id=provider_id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post("/browser-sessions/{session_id}/close", response_model=BrowserSessionRead)
async def close_browser_session(
    session_id: UUID,
    candidate_id: UUID,  # noqa: ARG001
    service: AuthenticationService = Depends(get_authentication_service),
):
    try:
        session = await service.browser_sessions.get(session_id)
        return await service.browser_sessions.close(session)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post("/browser-sessions/{session_id}/expire", response_model=BrowserSessionRead)
async def expire_browser_session(
    session_id: UUID,
    candidate_id: UUID,  # noqa: ARG001
    service: AuthenticationService = Depends(get_authentication_service),
):
    try:
        session = await service.browser_sessions.get(session_id)
        return await service.browser_sessions.mark_expired(session)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get("/secrets", response_model=list[SecretReferenceRead])
async def list_secret_references(
    candidate_id: UUID,  # noqa: ARG001
    provider_id: UUID | None = None,
    service: AuthenticationService = Depends(get_authentication_service),
):
    try:
        return await service.secrets.list(provider_id=provider_id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post("/secrets", response_model=SecretReferenceRead, status_code=status.HTTP_201_CREATED)
async def register_secret_reference(
    candidate_id: UUID,  # noqa: ARG001
    data: SecretReferenceRegister,
    service: AuthenticationService = Depends(get_authentication_service),
):
    try:
        return await service.secrets.register(
            data.provider_id,
            data.secret_type,
            data.external_reference,
            notes=data.notes,
        )
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post("/secrets/{reference_id}/rotate", response_model=SecretReferenceRead)
async def rotate_secret_reference(
    reference_id: UUID,
    candidate_id: UUID,  # noqa: ARG001
    service: AuthenticationService = Depends(get_authentication_service),
):
    try:
        reference = await service.secrets.get(reference_id)
        return await service.secrets.rotate(reference)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.post("/secrets/{reference_id}/revoke", response_model=SecretReferenceRead)
async def revoke_secret_reference(
    reference_id: UUID,
    candidate_id: UUID,  # noqa: ARG001
    service: AuthenticationService = Depends(get_authentication_service),
):
    try:
        reference = await service.secrets.get(reference_id)
        return await service.secrets.revoke(reference)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


@router.get("/secrets/{reference_id}/resolve", response_model=SecretReferenceResolveRead)
async def resolve_secret_reference(
    reference_id: UUID,
    candidate_id: UUID,  # noqa: ARG001
    service: AuthenticationService = Depends(get_authentication_service),
):
    """Resolve a reference via the configured secrets provider.

    Never returns the value; only reports availability. The local dev provider
    always reports `available=false`, so secrets cannot leak in development.
    """
    try:
        reference = await service.secrets.get(reference_id)
        resolution = await service.secrets.resolve(reference)
        return SecretReferenceResolveRead(
            available=resolution.available,
            local_dev=service.secrets.secrets_provider.name == "local-dev-placeholder",
        )
    except Exception as exc:
        raise handle_domain_error(exc) from exc
