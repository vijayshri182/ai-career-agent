"""Browser session manager.

Abstraction over browser sessions used to reach a provider. It never stores raw
cookies, tokens, or session payloads — only opaque references to encrypted
browser-state storage that lives outside the application database. It reports
authentication state back into the auth state machine via the caller.
"""

from datetime import UTC, datetime
from uuid import UUID

from backend.models.authentication import AuthProvider, AuthState
from backend.models.browser_session import BrowserSession, BrowserSessionStatus
from backend.repositories.audit import AuditRepository
from backend.repositories.authentication_provider import AuthProviderRepository
from backend.repositories.browser_session import BrowserSessionRepository

_TERMINAL_SESSION_STATES = frozenset(
    {BrowserSessionStatus.CLOSED, BrowserSessionStatus.EXPIRED}
)


class BrowserSessionManager:
    def __init__(
        self,
        repo: BrowserSessionRepository,
        provider_repo: AuthProviderRepository,
        audit_repo: AuditRepository,
        actor_id: UUID,
        candidate_id: UUID,
    ) -> None:
        self.repo = repo
        self.provider_repo = provider_repo
        self.audit_repo = audit_repo
        self.actor_id = actor_id
        self.candidate_id = candidate_id

    def _assert_owned(self) -> None:
        # Ownership is enforced by each repo lookup below (candidate scoping).
        pass

    async def _get_provider(self, provider_id: UUID) -> AuthProvider:
        return await self.provider_repo.get_for_candidate_or_404(
            provider_id, self.candidate_id
        )

    async def create(
        self,
        provider_id: UUID,
        storage_reference: str | None = None,
        external_session_id: str | None = None,
    ) -> BrowserSession:
        """Open a new browser session (no cookies stored here)."""
        await self._get_provider(provider_id)
        session = await self.repo.create(
            candidate_id=self.candidate_id,
            provider_id=provider_id,
            status=BrowserSessionStatus.ACTIVE,
            storage_reference=storage_reference,
            external_session_id=external_session_id,
            last_seen_at=datetime.now(UTC),
        )
        await self.audit_repo.log(
            event_type="BROWSER_SESSION_CREATED",
            actor_id=self.actor_id,
            candidate_id=self.candidate_id,
            entity_type="BrowserSession",
            entity_id=session.id,
            metadata={"provider_id": str(provider_id), "status": session.status.value},
        )
        return session

    async def obtain_or_create(
        self,
        provider_id: UUID,
        storage_reference: str | None = None,
        external_session_id: str | None = None,
    ) -> BrowserSession:
        """Reuse an active session for the provider, or create one."""
        active = await self.repo.get_active_for_provider(self.candidate_id, provider_id)
        if active is not None:
            return active
        return await self.create(
            provider_id,
            storage_reference=storage_reference,
            external_session_id=external_session_id,
        )

    async def check_status(
        self, session_id: UUID, provider_status: AuthState | None = None
    ) -> BrowserSession:
        """Touch a session and record the provider's observed auth state.

        Session lifecycle is owned by the caller (typically the auth state
        machine). Only the last-seen time is updated here; no cookies or
        tokens are read or stored.
        """
        session = await self.get(session_id)
        session.last_seen_at = datetime.now(UTC)
        await self.repo.update(session)
        return session

    async def mark_expired(self, session: BrowserSession) -> BrowserSession:
        if session.status in _TERMINAL_SESSION_STATES:
            return session
        session.status = BrowserSessionStatus.EXPIRED
        session.closed_at = datetime.now(UTC)
        await self.repo.update(session)
        await self.audit_repo.log(
            event_type="BROWSER_SESSION_EXPIRED",
            actor_id=self.actor_id,
            candidate_id=self.candidate_id,
            entity_type="BrowserSession",
            entity_id=session.id,
            metadata={"provider_id": str(session.provider_id)},
        )
        return session

    async def close(self, session: BrowserSession) -> BrowserSession:
        if session.status == BrowserSessionStatus.CLOSED:
            return session
        session.status = BrowserSessionStatus.CLOSED
        session.closed_at = datetime.now(UTC)
        await self.repo.update(session)
        await self.audit_repo.log(
            event_type="BROWSER_SESSION_CLOSED",
            actor_id=self.actor_id,
            candidate_id=self.candidate_id,
            entity_type="BrowserSession",
            entity_id=session.id,
            metadata={"provider_id": str(session.provider_id)},
        )
        return session

    async def suspend(self, session: BrowserSession) -> BrowserSession:
        if session.status == BrowserSessionStatus.SUSPENDED:
            return session
        session.status = BrowserSessionStatus.SUSPENDED
        await self.repo.update(session)
        await self.audit_repo.log(
            event_type="BROWSER_SESSION_SUSPENDED",
            actor_id=self.actor_id,
            candidate_id=self.candidate_id,
            entity_type="BrowserSession",
            entity_id=session.id,
            metadata={"provider_id": str(session.provider_id)},
        )
        return session

    async def report_session_expired(self, session_id: UUID) -> BrowserSession:
        """Mark a session expired because the site reported session expiry."""
        session = await self.get(session_id)
        return await self.mark_expired(session)

    async def get(self, session_id: UUID) -> BrowserSession:
        return await self.repo.get_for_candidate_or_404(session_id, self.candidate_id)

    async def list(self, provider_id: UUID | None = None) -> list[BrowserSession]:
        return await self.repo.list_by_candidate(self.candidate_id, provider_id=provider_id)
