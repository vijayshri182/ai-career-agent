"""Skill repository."""

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.candidate import CandidateSkill
from backend.repositories.base import BaseRepository


class SkillRepository(BaseRepository[CandidateSkill]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, CandidateSkill)
