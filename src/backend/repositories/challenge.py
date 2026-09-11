"""Challenge repository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import NotFoundError
from backend.models.challenge import Challenge, ChallengeStatus, ChallengeType
from backend.repositories.base import BaseRepository

IN_FLIGHT_STATUSES = (
    ChallengeStatus.OPEN,
    ChallengeStatus.ACKNOWLEDGED,
    ChallengeStatus.HUMAN_ACTION_REQUIRED,
)


class ChallengeRepository(BaseRepository[Challenge]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Challenge)

    async def list_by_candidate(
        self, candidate_id: UUID, status: ChallengeStatus | None = None
    ) -> list[Challenge]:
        stmt = select(Challenge).where(Challenge.candidate_id == candidate_id)
        if status is not None:
            stmt = stmt.where(Challenge.status == status)
        stmt = stmt.order_by(Challenge.detected_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_open_by_candidate(self, candidate_id: UUID) -> list[Challenge]:
        stmt = (
            select(Challenge)
            .where(Challenge.candidate_id == candidate_id)
            .where(Challenge.status.in_(IN_FLIGHT_STATUSES))
            .order_by(Challenge.detected_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_in_flight(
        self, provider_id: UUID, challenge_type: ChallengeType
    ) -> Challenge | None:
        stmt = (
            select(Challenge)
            .where(Challenge.provider_id == provider_id)
            .where(Challenge.challenge_type == challenge_type)
            .where(Challenge.status.in_(IN_FLIGHT_STATUSES))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_in_flight_by_provider(self, provider_id: UUID) -> list[Challenge]:
        stmt = (
            select(Challenge)
            .where(Challenge.provider_id == provider_id)
            .where(Challenge.status.in_(IN_FLIGHT_STATUSES))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_candidate_or_404(
        self, challenge_id: UUID, candidate_id: UUID
    ) -> Challenge:
        challenge = await self.get(challenge_id)
        if challenge is None or challenge.candidate_id != candidate_id:
            raise NotFoundError("Challenge not found")
        return challenge
