"""Learning / optimization repositories (feedback + recommendations)."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.learning import (
    Feedback,
    FeedbackOutcome,
    Recommendation,
    RecommendationKind,
    RecommendationStatus,
)
from backend.repositories.base import BaseRepository


class FeedbackRepository(BaseRepository[Feedback]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Feedback)

    async def get_for_candidate(self, feedback_id: UUID, candidate_id: UUID) -> Feedback | None:
        stmt = select(Feedback).where(
            Feedback.id == feedback_id,
            Feedback.candidate_id == candidate_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_candidate(
        self,
        candidate_id: UUID,
        *,
        outcome: FeedbackOutcome | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Feedback]:
        stmt = select(Feedback).where(Feedback.candidate_id == candidate_id)
        if outcome is not None:
            stmt = stmt.where(Feedback.outcome == outcome)
        stmt = stmt.order_by(Feedback.__table__.c.happened_at.desc()).limit(limit).offset(offset)
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_for_candidate(
        self,
        candidate_id: UUID,
        *,
        outcome: FeedbackOutcome | None = None,
    ) -> int:
        stmt = (
            select(func.count()).select_from(Feedback).where(Feedback.candidate_id == candidate_id)
        )
        if outcome is not None:
            stmt = stmt.where(Feedback.outcome == outcome)
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_by_outcome(
        self, candidate_id: UUID
    ) -> dict[FeedbackOutcome, int]:
        stmt = (
            select(Feedback.outcome, func.count())
            .select_from(Feedback)
            .where(Feedback.candidate_id == candidate_id)
            .group_by(Feedback.outcome)
        )
        rows = (await self.session.execute(stmt)).all()
        return {FeedbackOutcome(outcome): int(count) for outcome, count in rows}


class RecommendationRepository(BaseRepository[Recommendation]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Recommendation)

    async def get_for_candidate(
        self, recommendation_id: UUID, candidate_id: UUID
    ) -> Recommendation | None:
        stmt = select(Recommendation).where(
            Recommendation.id == recommendation_id,
            Recommendation.candidate_id == candidate_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_key(
        self, candidate_id: UUID, kind: RecommendationKind, source_key: str
    ) -> Recommendation | None:
        stmt = select(Recommendation).where(
            Recommendation.candidate_id == candidate_id,
            Recommendation.kind == kind,
            Recommendation.source_key == source_key,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_candidate(
        self,
        candidate_id: UUID,
        *,
        status: RecommendationStatus | None = None,
        kind: RecommendationKind | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Recommendation]:
        stmt = select(Recommendation).where(Recommendation.candidate_id == candidate_id)
        if status is not None:
            stmt = stmt.where(Recommendation.status == status)
        if kind is not None:
            stmt = stmt.where(Recommendation.kind == kind)
        stmt = stmt.order_by(Recommendation.__table__.c.created_at.desc()).limit(limit).offset(offset)
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_for_candidate(
        self,
        candidate_id: UUID,
        *,
        status: RecommendationStatus | None = None,
        kind: RecommendationKind | None = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(Recommendation)
            .where(Recommendation.candidate_id == candidate_id)
        )
        if status is not None:
            stmt = stmt.where(Recommendation.status == status)
        if kind is not None:
            stmt = stmt.where(Recommendation.kind == kind)
        return int((await self.session.execute(stmt)).scalar_one())
