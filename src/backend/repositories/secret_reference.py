"""Secret reference repository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import NotFoundError
from backend.models.secret_reference import SecretReference
from backend.repositories.base import BaseRepository


class SecretReferenceRepository(BaseRepository[SecretReference]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SecretReference)

    async def list_by_candidate(
        self, candidate_id: UUID, provider_id: UUID | None = None
    ) -> list[SecretReference]:
        stmt = select(SecretReference).where(SecretReference.candidate_id == candidate_id)
        if provider_id is not None:
            stmt = stmt.where(SecretReference.provider_id == provider_id)
        stmt = stmt.order_by(SecretReference.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_candidate_or_404(
        self, reference_id: UUID, candidate_id: UUID
    ) -> SecretReference:
        ref = await self.get(reference_id)
        if ref is None or ref.candidate_id != candidate_id:
            raise NotFoundError("Secret reference not found")
        return ref
