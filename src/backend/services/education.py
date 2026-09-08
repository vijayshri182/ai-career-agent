"""Education service."""

from uuid import UUID

from backend.core.exceptions import NotFoundError
from backend.models.candidate import Education
from backend.repositories.audit import AuditRepository
from backend.repositories.education import EducationRepository
from backend.schemas.education import EducationCreate, EducationUpdate


class EducationService:
    def __init__(self, repo: EducationRepository, audit_repo: AuditRepository) -> None:
        self.repo = repo
        self.audit_repo = audit_repo

    async def list(self, candidate_id: UUID) -> list[Education]:
        return await self.repo.list_ordered(candidate_id)

    async def get(self, candidate_id: UUID, education_id: UUID) -> Education:
        edu = await self.repo.get(education_id)
        if edu is None or edu.candidate_id != candidate_id:
            raise NotFoundError("Education not found")
        return edu

    async def add(
        self, candidate_id: UUID, user_id: UUID, data: EducationCreate
    ) -> Education:
        edu = await self.repo.create(candidate_id=candidate_id, **data.model_dump())
        await self.audit_repo.log(
            event_type="EDUCATION_ADDED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="Education",
            entity_id=edu.id,
            metadata={"institution": data.institution, "degree": data.degree},
        )
        return edu

    async def update(
        self, candidate_id: UUID, user_id: UUID, education_id: UUID, data: EducationUpdate
    ) -> Education:
        edu = await self.get(candidate_id, education_id)
        edu = await self.repo.update(edu, **data.model_dump(exclude_unset=True))
        await self.audit_repo.log(
            event_type="EDUCATION_UPDATED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="Education",
            entity_id=edu.id,
        )
        return edu

    async def delete(self, candidate_id: UUID, user_id: UUID, education_id: UUID) -> None:
        edu = await self.get(candidate_id, education_id)
        await self.repo.delete(edu)
        await self.audit_repo.log(
            event_type="EDUCATION_DELETED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="Education",
            entity_id=edu.id,
        )
