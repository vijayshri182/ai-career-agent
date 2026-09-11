"""Authentication provider and state repositories."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import NotFoundError
from backend.models.authentication import AuthProvider, AuthProviderState
from backend.repositories.base import BaseRepository


class AuthProviderRepository(BaseRepository[AuthProvider]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AuthProvider)

    async def list_by_candidate(self, candidate_id: UUID) -> list[AuthProvider]:
        stmt = select(AuthProvider).where(
            AuthProvider.candidate_id == candidate_id
        ).order_by(AuthProvider.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_candidate_or_404(
        self, provider_id: UUID, candidate_id: UUID
    ) -> AuthProvider:
        provider = await self.get(provider_id)
        if provider is None or provider.candidate_id != candidate_id:
            raise NotFoundError("Authentication provider not found")
        return provider

    async def name_exists(self, candidate_id: UUID, name: str) -> bool:
        stmt = select(AuthProvider.id).where(
            AuthProvider.candidate_id == candidate_id, AuthProvider.name == name
        )
        result = await self.session.execute(stmt)
        return result.first() is not None


class AuthStateRepository(BaseRepository[AuthProviderState]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AuthProviderState)

    async def get_by_provider(self, provider_id: UUID) -> AuthProviderState | None:
        stmt = select(AuthProviderState).where(
            AuthProviderState.provider_id == provider_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_provider_or_404(self, provider_id: UUID) -> AuthProviderState:
        state = await self.get_by_provider(provider_id)
        if state is None:
            raise NotFoundError("Authentication state not found")
        return state
