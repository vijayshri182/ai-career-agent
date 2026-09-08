"""Candidate profile service."""

from uuid import UUID

from backend.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from backend.models.candidate import Candidate, ProfileStatus
from backend.repositories.audit import AuditRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.user import UserRepository
from backend.schemas.candidate import CandidateCreate, CandidateUpdate
from backend.schemas.preferences import CareerPreferences


class CandidateService:
    def __init__(
        self,
        candidate_repo: CandidateRepository,
        audit_repo: AuditRepository,
        user_repo: UserRepository,
    ) -> None:
        self.candidate_repo = candidate_repo
        self.audit_repo = audit_repo
        self.user_repo = user_repo

    async def create_candidate(self, user_id: UUID, data: CandidateCreate) -> Candidate:
        existing = await self.candidate_repo.get_active_by_user(user_id)
        if existing:
            raise ValidationError("Candidate profile already exists for this user")
        candidate = await self.candidate_repo.create_for_user(
            user_id=user_id, **data.model_dump()
        )
        await self.audit_repo.log(
            event_type="PROFILE_CREATED",
            actor_id=user_id,
            candidate_id=candidate.id,
            entity_type="Candidate",
            entity_id=candidate.id,
        )
        return candidate

    async def get_my_candidate(self, user_id: UUID) -> Candidate:
        candidate = await self.candidate_repo.get_active_by_user(user_id)
        if candidate is None:
            raise NotFoundError("Candidate profile not found")
        return candidate

    async def get_candidate(self, candidate_id: UUID, user_id: UUID) -> Candidate:
        candidate = await self.candidate_repo.get_for_user_or_404(candidate_id, user_id)
        return candidate

    async def update_candidate(
        self, candidate_id: UUID, user_id: UUID, data: CandidateUpdate
    ) -> Candidate:
        candidate = await self.candidate_repo.get_for_user_or_404(candidate_id, user_id)
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            raise ValidationError("No fields provided for update")
        candidate = await self.candidate_repo.update_candidate(candidate, **update_data)
        await self.audit_repo.log(
            event_type="PROFILE_UPDATED",
            actor_id=user_id,
            candidate_id=candidate.id,
            entity_type="Candidate",
            entity_id=candidate.id,
            metadata={"fields": list(update_data.keys())},
        )
        return candidate

    async def deactivate_candidate(self, candidate_id: UUID, user_id: UUID) -> Candidate:
        candidate = await self.candidate_repo.get_for_user_or_404(candidate_id, user_id)
        candidate = await self.candidate_repo.update_candidate(
            candidate, status=ProfileStatus.DELETED
        )
        await self.audit_repo.log(
            event_type="PROFILE_DEACTIVATED",
            actor_id=user_id,
            candidate_id=candidate.id,
            entity_type="Candidate",
            entity_id=candidate.id,
        )
        return candidate

    async def update_preferences(
        self, candidate_id: UUID, user_id: UUID, preferences: CareerPreferences
    ) -> Candidate:
        candidate = await self.candidate_repo.get_for_user_or_404(candidate_id, user_id)
        candidate = await self.candidate_repo.update_candidate(
            candidate, career_preferences=preferences.model_dump()
        )
        await self.audit_repo.log(
            event_type="PREFERENCES_UPDATED",
            actor_id=user_id,
            candidate_id=candidate.id,
            entity_type="Candidate",
            entity_id=candidate.id,
        )
        return candidate

    async def enforce_ownership(self, candidate_id: UUID, user_id: UUID) -> None:
        candidate = await self.candidate_repo.get(candidate_id)
        if candidate is None or candidate.user_id != user_id:
            raise ForbiddenError("You do not have access to this candidate")
