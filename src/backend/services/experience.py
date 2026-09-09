"""Experience service."""

from uuid import UUID

from backend.core.exceptions import NotFoundError
from backend.models.candidate import Experience
from backend.repositories.audit import AuditRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.experience import ExperienceRepository
from backend.schemas.experience import ExperienceCreate, ExperienceUpdate


class ExperienceService:
    def __init__(
        self,
        repo: ExperienceRepository,
        audit_repo: AuditRepository,
        candidate_repo: CandidateRepository,
    ) -> None:
        self.repo = repo
        self.audit_repo = audit_repo
        self.candidate_repo = candidate_repo

    async def _assert_candidate_owned(self, candidate_id: UUID, user_id: UUID) -> None:
        await self.candidate_repo.get_for_user_or_404(candidate_id, user_id)

    async def list(self, candidate_id: UUID, user_id: UUID) -> list[Experience]:
        await self._assert_candidate_owned(candidate_id, user_id)
        return await self.repo.list_ordered(candidate_id)

    async def get(
        self, candidate_id: UUID, user_id: UUID, experience_id: UUID
    ) -> Experience:
        await self._assert_candidate_owned(candidate_id, user_id)
        exp = await self.repo.get(experience_id)
        if exp is None or exp.candidate_id != candidate_id:
            raise NotFoundError("Experience not found")
        return exp

    async def add(
        self, candidate_id: UUID, user_id: UUID, data: ExperienceCreate
    ) -> Experience:
        await self._assert_candidate_owned(candidate_id, user_id)
        exp = await self.repo.create(candidate_id=candidate_id, **data.model_dump())
        await self.audit_repo.log(
            event_type="EXPERIENCE_ADDED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="Experience",
            entity_id=exp.id,
            metadata={"company": data.company_name, "title": data.title},
        )
        return exp

    async def update(
        self, candidate_id: UUID, user_id: UUID, experience_id: UUID, data: ExperienceUpdate
    ) -> Experience:
        exp = await self.get(candidate_id, user_id, experience_id)
        exp = await self.repo.update(exp, **data.model_dump(exclude_unset=True))
        await self.audit_repo.log(
            event_type="EXPERIENCE_UPDATED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="Experience",
            entity_id=exp.id,
        )
        return exp

    async def delete(self, candidate_id: UUID, user_id: UUID, experience_id: UUID) -> None:
        exp = await self.get(candidate_id, user_id, experience_id)
        await self.repo.delete(exp)
        await self.audit_repo.log(
            event_type="EXPERIENCE_DELETED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="Experience",
            entity_id=exp.id,
        )
