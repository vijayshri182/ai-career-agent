"""Authentication provider service (CRUD + state transitions)."""

from datetime import UTC, datetime
from uuid import UUID

from backend.core.exceptions import NotFoundError, ValidationError
from backend.models.authentication import (
    AuthProvider,
    AuthProviderState,
    AuthState,
)
from backend.repositories.audit import AuditRepository
from backend.repositories.authentication_provider import (
    AuthProviderRepository,
    AuthStateRepository,
)
from backend.repositories.candidate import CandidateRepository
from backend.schemas.authentication import ProviderCreate, ProviderUpdate
from backend.services.authentication_state import AuthStateMachine


class AuthProviderService:
    def __init__(
        self,
        provider_repo: AuthProviderRepository,
        state_repo: AuthStateRepository,
        candidate_repo: CandidateRepository,
        audit_repo: AuditRepository,
        actor_id: UUID,
        candidate_id: UUID,
    ) -> None:
        self.provider_repo = provider_repo
        self.state_repo = state_repo
        self.candidate_repo = candidate_repo
        self.audit_repo = audit_repo
        self.actor_id = actor_id
        self.candidate_id = candidate_id

    async def _assert_owned(self) -> None:
        await self.candidate_repo.get_for_user_or_404(self.candidate_id, self.actor_id)

    async def list(self) -> list[AuthProvider]:
        await self._assert_owned()
        return await self.provider_repo.list_by_candidate(self.candidate_id)

    async def get(self, provider_id: UUID) -> AuthProvider:
        await self._assert_owned()
        return await self.provider_repo.get_for_candidate_or_404(
            provider_id, self.candidate_id
        )

    async def create(self, data: ProviderCreate) -> AuthProvider:
        await self._assert_owned()
        name = data.name.strip()
        if not name:
            raise ValidationError("Provider name is required")
        if await self.provider_repo.name_exists(self.candidate_id, name):
            raise ValidationError("An authentication provider with this name already exists")
        provider = await self.provider_repo.create(
            candidate_id=self.candidate_id,
            name=name,
            provider_type=data.provider_type,
            base_url=data.base_url,
            authentication_method=data.authentication_method,
            is_enabled=data.is_enabled,
            notes=data.notes,
            metadata_json=data.metadata,
        )
        await self.state_repo.create(
            provider_id=provider.id,
            status=AuthStateMachine.initial_state(data.authentication_method),
            checked_at=datetime.now(UTC),
        )
        await self.audit_repo.log(
            event_type="AUTH_PROVIDER_CREATED",
            actor_id=self.actor_id,
            candidate_id=self.candidate_id,
            entity_type="AuthProvider",
            entity_id=provider.id,
            metadata={"name": name, "method": data.authentication_method.value},
        )
        return provider

    async def update(
        self, provider_id: UUID, data: ProviderUpdate
    ) -> AuthProvider:
        provider = await self.get(provider_id)
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            raise ValidationError("No fields provided for update")
        if "name" in update_data:
            new_name = update_data["name"]
            if new_name and new_name != provider.name and await self.provider_repo.name_exists(
                self.candidate_id, new_name
            ):
                raise ValidationError("An authentication provider with this name already exists")
        provider = await self.provider_repo.update(provider, **update_data)
        await self.audit_repo.log(
            event_type="AUTH_PROVIDER_UPDATED",
            actor_id=self.actor_id,
            candidate_id=self.candidate_id,
            entity_type="AuthProvider",
            entity_id=provider.id,
            metadata={"fields": list(update_data.keys())},
        )
        return provider

    async def delete(self, provider_id: UUID) -> None:
        provider = await self.get(provider_id)
        state = await self.state_repo.get_by_provider(provider_id)
        if state is not None:
            await self.state_repo.delete(state)
        await self.provider_repo.delete(provider)
        await self.audit_repo.log(
            event_type="AUTH_PROVIDER_DELETED",
            actor_id=self.actor_id,
            candidate_id=self.candidate_id,
            entity_type="AuthProvider",
            entity_id=provider.id,
            metadata={"name": provider.name},
        )

    async def apply_state(
        self,
        provider: AuthProvider,
        status: AuthState,
        metadata: dict[str, object] | None = None,
        session_reference: str | None = None,
    ) -> AuthProviderState:
        """Transition the provider to a new state via the state machine."""
        state = await self.state_repo.get_by_provider(provider.id)
        if state is None:
            raise NotFoundError("Authentication state not found")
        previous = state.status
        if previous != status:
            AuthStateMachine.transition(previous, status)
        now = datetime.now(UTC)
        state.status = status
        state.checked_at = now
        if status == AuthState.AUTHENTICATED:
            state.authenticated_at = now
        if session_reference is not None:
            state.session_reference = session_reference
        state.state_metadata = {
            **(state.state_metadata or {}),
            **(metadata or {}),
        }
        await self.state_repo.update(state)
        if previous != status:
            await self.audit_repo.log(
                event_type="AUTH_STATE_CHANGED",
                actor_id=self.actor_id,
                candidate_id=self.candidate_id,
                entity_type="AuthProvider",
                entity_id=provider.id,
                result="success",
                metadata={
                    "provider_id": str(provider.id),
                    "from": previous.value,
                    "to": status.value,
                },
            )
        else:
            await self.audit_repo.log(
                event_type="AUTH_STATE_REFRESHED",
                actor_id=self.actor_id,
                candidate_id=self.candidate_id,
                entity_type="AuthProvider",
                entity_id=provider.id,
                result="already",
                metadata={"provider_id": str(provider.id), "status": status.value},
            )
        return state

    async def get_state(self, provider_id: UUID) -> AuthProviderState:
        await self.get(provider_id)
        return await self.state_repo.get_for_provider_or_404(provider_id)

    async def set_session_reference(
        self, provider_id: UUID, session_reference: str
    ) -> AuthProviderState:
        provider = await self.get(provider_id)
        state = await self.state_repo.get_by_provider(provider.id)
        if state is None:
            raise NotFoundError("Authentication state not found")
        state.session_reference = session_reference
        state.checked_at = datetime.now(UTC)
        await self.state_repo.update(state)
        await self.audit_repo.log(
            event_type="AUTH_SESSION_UPDATED",
            actor_id=self.actor_id,
            candidate_id=self.candidate_id,
            entity_type="AuthProvider",
            entity_id=provider.id,
            result="success",
            metadata={"provider_id": str(provider.id)},
        )
        return state
