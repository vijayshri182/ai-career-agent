"""Recruiter contact repositories."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.recruiter_contact import ContactSource, RecruiterContact
from backend.repositories.base import BaseRepository


class ContactSourceRepository(BaseRepository[ContactSource]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ContactSource)


class RecruiterContactRepository(BaseRepository[RecruiterContact]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RecruiterContact)

    async def get_for_candidate(self, contact_id: UUID, candidate_id: UUID) -> RecruiterContact | None:
        stmt = select(RecruiterContact).where(
            RecruiterContact.id == contact_id,
            RecruiterContact.candidate_id == candidate_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_profile_url(self, candidate_id: UUID, profile_url: str) -> RecruiterContact | None:
        stmt = select(RecruiterContact).where(
            RecruiterContact.candidate_id == candidate_id,
            RecruiterContact.public_profile_url == profile_url,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_candidate(
        self,
        candidate_id: UUID,
        *,
        company_id: UUID | None = None,
        job_id: UUID | None = None,
        surfaced_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RecruiterContact]:
        stmt = select(RecruiterContact).where(RecruiterContact.candidate_id == candidate_id)
        if company_id is not None:
            stmt = stmt.where(RecruiterContact.company_id == company_id)
        if job_id is not None:
            stmt = stmt.where(RecruiterContact.job_id == job_id)
        if surfaced_only:
            stmt = stmt.where(RecruiterContact.is_suppressed.is_(False))
        stmt = (
            stmt.order_by(RecruiterContact.__table__.c.confidence_score.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_for_candidate(
        self,
        candidate_id: UUID,
        *,
        company_id: UUID | None = None,
        job_id: UUID | None = None,
        surfaced_only: bool = True,
    ) -> int:
        stmt = select(func.count()).select_from(RecruiterContact).where(
            RecruiterContact.candidate_id == candidate_id
        )
        if company_id is not None:
            stmt = stmt.where(RecruiterContact.company_id == company_id)
        if job_id is not None:
            stmt = stmt.where(RecruiterContact.job_id == job_id)
        if surfaced_only:
            stmt = stmt.where(RecruiterContact.is_suppressed.is_(False))
        return int((await self.session.execute(stmt)).scalar_one())
