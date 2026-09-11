"""FastAPI dependencies."""

from collections.abc import AsyncGenerator
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import Settings, get_settings
from backend.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from backend.core.security_service import get_security_service
from backend.db.engine import make_engine, make_session_factory
from backend.models.candidate import Candidate
from backend.models.user import User
from backend.repositories.audit import AuditRepository
from backend.repositories.authentication_provider import (
    AuthProviderRepository,
    AuthStateRepository,
)
from backend.repositories.browser_session import BrowserSessionRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.certification import CertificationRepository
from backend.repositories.challenge import ChallengeRepository
from backend.repositories.education import EducationRepository
from backend.repositories.experience import ExperienceRepository
from backend.repositories.resume import (
    ParsedResumeRepository,
    ResumeRepository,
    ResumeVersionRepository,
)
from backend.repositories.secret_reference import SecretReferenceRepository
from backend.repositories.skill import SkillRepository
from backend.repositories.user import UserRepository
from backend.repositories.workflow_run import WorkflowRunRepository
from backend.services.auth import AuthService
from backend.services.authentication import AuthenticationService
from backend.services.authentication_provider import AuthProviderService
from backend.services.browser_session import BrowserSessionManager
from backend.services.candidate import CandidateService
from backend.services.certification import CertificationService
from backend.services.challenge import ChallengeService
from backend.services.education import EducationService
from backend.services.experience import ExperienceService
from backend.services.human_in_loop import HumanInTheLoopService
from backend.services.profile import ProfileService
from backend.services.resume import ResumeService
from backend.services.secrets import LocalSecretsProvider, SecretReferenceService
from backend.services.skill import SkillService
from backend.services.storage import make_storage

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

_engine = None


def _get_engine(settings: Settings):
    global _engine
    if _engine is None:
        _engine = make_engine(settings)
    return _engine


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    settings = get_settings()
    engine = _get_engine(settings)
    async_session = make_session_factory(engine)
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_current_user_id(
    token: str | None = Depends(oauth2_scheme),
    settings: Settings = Depends(get_settings),
) -> UUID:
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    try:
        payload = get_security_service(settings).decode_access_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        return UUID(user_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from exc


async def get_current_user(
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> User:
    repo = UserRepository(session)
    user = await repo.get(user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user


async def get_owned_candidate(
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Candidate:
    """Resolve candidate_id to the authenticated user's own candidate.

    Applies to every sub-resource route so cross-user and non-existent
    candidates are indistinguishable (404). Reuses the existing
    CandidateRepository.get_for_user_or_404 authorization rule.
    """
    try:
        return await CandidateRepository(session).get_for_user_or_404(candidate_id, user_id)
    except Exception as exc:
        raise handle_domain_error(exc) from exc


async def get_auth_service(session: AsyncSession = Depends(get_session)) -> AuthService:
    return AuthService(UserRepository(session))


async def get_candidate_service(session: AsyncSession = Depends(get_session)) -> CandidateService:
    return CandidateService(
        CandidateRepository(session),
        AuditRepository(session),
        UserRepository(session),
    )


async def get_skill_service(session: AsyncSession = Depends(get_session)) -> SkillService:
    return SkillService(
        SkillRepository(session),
        AuditRepository(session),
        CandidateRepository(session),
    )


async def get_experience_service(
    session: AsyncSession = Depends(get_session),
) -> ExperienceService:
    return ExperienceService(
        ExperienceRepository(session),
        AuditRepository(session),
        CandidateRepository(session),
    )


async def get_education_service(
    session: AsyncSession = Depends(get_session),
) -> EducationService:
    return EducationService(
        EducationRepository(session),
        AuditRepository(session),
        CandidateRepository(session),
    )


async def get_certification_service(
    session: AsyncSession = Depends(get_session),
) -> CertificationService:
    return CertificationService(
        CertificationRepository(session),
        AuditRepository(session),
        CandidateRepository(session),
    )


async def get_resume_service(session: AsyncSession = Depends(get_session)) -> ResumeService:
    settings = get_settings()
    return ResumeService(
        ResumeRepository(session),
        ResumeVersionRepository(session),
        ParsedResumeRepository(session),
        AuditRepository(session),
        CandidateRepository(session),
        SkillRepository(session),
        storage=make_storage(settings),
        settings=settings,
    )


async def get_profile_service(session: AsyncSession = Depends(get_session)) -> ProfileService:
    return ProfileService(
        CandidateRepository(session),
        SkillRepository(session),
        ExperienceRepository(session),
        EducationRepository(session),
        CertificationRepository(session),
        ResumeRepository(session),
    )


async def get_authentication_service(
    candidate_id: UUID,
    candidate: Candidate = Depends(get_owned_candidate),
    session: AsyncSession = Depends(get_session),
) -> AuthenticationService:
    """Build candidate-scoped authentication services.

    Ownership is enforced at the HTTP layer via `get_owned_candidate` (404 for
    cross-user/non-existent candidates); services re-check ownership as
    defense-in-depth.
    """
    actor_id = candidate.user_id
    audit_repo = AuditRepository(session)
    candidate_repo = CandidateRepository(session)
    provider_repo = AuthProviderRepository(session)
    state_repo = AuthStateRepository(session)
    workflow_repo = WorkflowRunRepository(session)
    challenge_repo = ChallengeRepository(session)
    browser_repo = BrowserSessionRepository(session)
    secret_repo = SecretReferenceRepository(session)

    provider_service = AuthProviderService(
        provider_repo, state_repo, candidate_repo, audit_repo, actor_id, candidate.id
    )
    workflow_service = HumanInTheLoopService(
        workflow_repo, audit_repo, actor_id, candidate.id
    )
    challenge_service = ChallengeService(
        challenge_repo, audit_repo, provider_service, workflow_service, actor_id, candidate.id
    )
    browser_manager = BrowserSessionManager(
        browser_repo, provider_repo, audit_repo, actor_id, candidate.id
    )
    secret_service = SecretReferenceService(
        secret_repo, audit_repo, LocalSecretsProvider(), actor_id, candidate.id
    )
    return AuthenticationService(
        providers=provider_service,
        challenges=challenge_service,
        workflows=workflow_service,
        browser_sessions=browser_manager,
        secrets=secret_service,
    )


def handle_domain_error(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, ForbiddenError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    raise exc
