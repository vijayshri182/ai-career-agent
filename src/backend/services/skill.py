"""Skill service."""

from uuid import UUID

from backend.core.exceptions import NotFoundError
from backend.models.candidate import CandidateSkill
from backend.repositories.audit import AuditRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.skill import SkillRepository
from backend.schemas.skill import SkillCreate, SkillUpdate


class SkillService:
    def __init__(
        self,
        repo: SkillRepository,
        audit_repo: AuditRepository,
        candidate_repo: CandidateRepository,
    ) -> None:
        self.repo = repo
        self.audit_repo = audit_repo
        self.candidate_repo = candidate_repo

    async def _assert_candidate_owned(self, candidate_id: UUID, user_id: UUID) -> None:
        await self.candidate_repo.get_for_user_or_404(candidate_id, user_id)

    async def list(self, candidate_id: UUID, user_id: UUID) -> list[CandidateSkill]:
        await self._assert_candidate_owned(candidate_id, user_id)
        return await self.repo.list(candidate_id=candidate_id)

    async def get(
        self, candidate_id: UUID, user_id: UUID, skill_id: UUID
    ) -> CandidateSkill:
        await self._assert_candidate_owned(candidate_id, user_id)
        skill = await self.repo.get(skill_id)
        if skill is None or skill.candidate_id != candidate_id:
            raise NotFoundError("Skill not found")
        return skill

    async def add(self, candidate_id: UUID, user_id: UUID, data: SkillCreate) -> CandidateSkill:
        await self._assert_candidate_owned(candidate_id, user_id)
        skill = await self.repo.create(candidate_id=candidate_id, **data.model_dump())
        await self.audit_repo.log(
            event_type="SKILL_ADDED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="CandidateSkill",
            entity_id=skill.id,
            metadata={"name": data.name},
        )
        return skill

    async def update(
        self, candidate_id: UUID, user_id: UUID, skill_id: UUID, data: SkillUpdate
    ) -> CandidateSkill:
        skill = await self.get(candidate_id, user_id, skill_id)
        skill = await self.repo.update(skill, **data.model_dump(exclude_unset=True))
        await self.audit_repo.log(
            event_type="SKILL_UPDATED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="CandidateSkill",
            entity_id=skill.id,
        )
        return skill

    async def delete(self, candidate_id: UUID, user_id: UUID, skill_id: UUID) -> None:
        skill = await self.get(candidate_id, user_id, skill_id)
        await self.repo.delete(skill)
        await self.audit_repo.log(
            event_type="SKILL_DELETED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="CandidateSkill",
            entity_id=skill.id,
            metadata={"name": skill.name},
        )
