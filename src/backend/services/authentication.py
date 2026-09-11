"""Authentication & Challenge Management facade.

Provides a single entry-point that wires providers, challenges, workflows,
browser sessions, and secrets behind the routes. The key method
`observe_state` safely translates a state report into the appropriate
challenge/workflow lifecycle actions with full idempotency guarantees.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from backend.models.authentication import AuthProviderState, AuthState
from backend.services.authentication_provider import AuthProviderService
from backend.services.browser_session import BrowserSessionManager
from backend.services.challenge import ChallengeService
from backend.services.challenge_detection import challenge_type_for_state
from backend.services.human_in_loop import HumanInTheLoopService
from backend.services.secrets import SecretReferenceService


@dataclass(frozen=True)
class AuthOverview:
    provider_count: int
    open_challenge_count: int
    providers: list["ProviderOverview"]
    open_challenges: list["ChallengeSummary"]


@dataclass(frozen=True)
class ProviderOverview:
    id: UUID
    name: str
    provider_type: str
    authentication_method: str
    is_enabled: bool
    auth_status: str
    authenticated_at: datetime | None
    last_checked: datetime
    session_reference: str | None


@dataclass(frozen=True)
class ChallengeSummary:
    id: UUID
    provider_id: UUID
    challenge_type: str
    status: str
    severity: str
    human_required: bool
    detected_at: datetime
    expires_at: datetime | None


class AuthenticationService:
    def __init__(
        self,
        providers: AuthProviderService,
        challenges: ChallengeService,
        workflows: HumanInTheLoopService,
        browser_sessions: BrowserSessionManager,
        secrets: SecretReferenceService,
    ) -> None:
        self.providers = providers
        self.challenges = challenges
        self.workflows = workflows
        self.browser_sessions = browser_sessions
        self.secrets = secrets

    async def observe_state(
        self,
        provider_id: UUID,
        status: AuthState,
        metadata: dict[str, object] | None = None,
        session_reference: str | None = None,
    ) -> AuthProviderState:
        """Translate a raw state observation into auth state + challenge
        lifecycle actions. Safe to call repeatedly with the same status
        (idempotent via challenge deduplication and state transition guards).
        """
        provider = await self.providers.get(provider_id)
        current = await self.providers.get_state(provider.id)
        was_escalating = current.status in {
            AuthState.MFA_REQUIRED,
            AuthState.CAPTCHA_REQUIRED,
            AuthState.ACCESS_BLOCKED,
            AuthState.HUMAN_ACTION_REQUIRED,
        }
        state = await self.providers.apply_state(
            provider, status, metadata=metadata, session_reference=session_reference
        )

        # Close in-flight challenges automatically when the session becomes
        # authenticated again (e.g. human resolved the issue elsewhere).
        if status in (AuthState.AUTHENTICATED, AuthState.NOT_REQUIRED):
            await self.challenges.resolve_superseded(provider)
            return state

        # Create or escalate a challenge for states that require human
        # verification.
        ct = challenge_type_for_state(status)
        if ct is not None:
            challenge = await self.challenges.ensure_open(
                provider,
                ct,
                description=f"Observed state: {status.value}",
                metadata=metadata,
            )
            if was_escalating:
                # Re-escalate if the same challenge persists across
                # repeat reports (e.g. workflow resumed but site still
                # presenting a CAPTCHA).
                await self.challenges.escalate(challenge)

        return state

    async def overview(self) -> AuthOverview:
        """High-level dashboard view: providers + their states + open challenges."""
        providers = await self.providers.list()
        provider_overviews = []
        for p in providers:
            state = await self.providers.get_state(p.id)
            provider_overviews.append(
                ProviderOverview(
                    id=p.id,
                    name=p.name,
                    provider_type=p.provider_type.value,
                    authentication_method=p.authentication_method.value,
                    is_enabled=p.is_enabled,
                    auth_status=state.status.value,
                    authenticated_at=state.authenticated_at,
                    last_checked=state.checked_at,
                    session_reference=state.session_reference,
                )
            )

        challenges = await self.challenges.list(open_only=True)
        challenge_summaries = [
            ChallengeSummary(
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

        return AuthOverview(
            provider_count=len(providers),
            open_challenge_count=len(challenges),
            providers=provider_overviews,
            open_challenges=challenge_summaries,
        )
