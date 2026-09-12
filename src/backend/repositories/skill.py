"""Skill repository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.candidate import CandidateSkill
from backend.repositories.base import BaseRepository


class SkillRepository(BaseRepository[CandidateSkill]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, CandidateSkill)

    async def list_for_candidate(self, candidate_id: UUID) -> list[CandidateSkill]:
        stmt = select(CandidateSkill).where(CandidateSkill.candidate_id == candidate_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
