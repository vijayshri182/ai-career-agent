"""Browser session repository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import NotFoundError
from backend.models.browser_session import BrowserSession, BrowserSessionStatus
from backend.repositories.base import BaseRepository


class BrowserSessionRepository(BaseRepository[BrowserSession]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BrowserSession)

    async def list_by_candidate(
        self, candidate_id: UUID, provider_id: UUID | None = None
    ) -> list[BrowserSession]:
        stmt = select(BrowserSession).where(BrowserSession.candidate_id == candidate_id)
        if provider_id is not None:
            stmt = stmt.where(BrowserSession.provider_id == provider_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_for_provider(
        self, candidate_id: UUID, provider_id: UUID
    ) -> BrowserSession | None:
        stmt = (
            select(BrowserSession)
            .where(BrowserSession.candidate_id == candidate_id)
            .where(BrowserSession.provider_id == provider_id)
            .where(BrowserSession.status == BrowserSessionStatus.ACTIVE)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_for_candidate_or_404(
        self, session_id: UUID, candidate_id: UUID
    ) -> BrowserSession:
        session = await self.get(session_id)
        if session is None or session.candidate_id != candidate_id:
            raise NotFoundError("Browser session not found")
        return session
