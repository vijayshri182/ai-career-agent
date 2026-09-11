"""Job source CRUD service."""

from uuid import UUID

from backend.core.exceptions import NotFoundError
from backend.models.job_source import JobSource
from backend.repositories.audit import AuditRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.job_source import JobSourceRepository
from backend.schemas.job_source import JobSourceCreate, JobSourceUpdate
from backend.services.url_validation import validate_source_url


class JobSourceService:
    def __init__(
        self,
        repo: JobSourceRepository,
        audit_repo: AuditRepository,
        candidate_repo: CandidateRepository,
    ) -> None:
        self.repo = repo
        self.audit_repo = audit_repo
        self.candidate_repo = candidate_repo

    async def _assert_candidate_owned(self, candidate_id: UUID, user_id: UUID) -> None:
        await self.candidate_repo.get_for_user_or_404(candidate_id, user_id)

    async def list(self, candidate_id: UUID, user_id: UUID) -> list[JobSource]:
        await self._assert_candidate_owned(candidate_id, user_id)
        return await self.repo.list_for_candidate(candidate_id)

    async def get(
        self, candidate_id: UUID, user_id: UUID, source_id: UUID
    ) -> JobSource:
        await self._assert_candidate_owned(candidate_id, user_id)
        source = await self.repo.get_for_candidate(source_id, candidate_id)
        if source is None:
            raise NotFoundError("Job source not found")
        return source

    async def create(
        self, candidate_id: UUID, user_id: UUID, data: JobSourceCreate
    ) -> JobSource:
        await self._assert_candidate_owned(candidate_id, user_id)
        validate_source_url(data.base_url)
        source = await self.repo.create(
            candidate_id=candidate_id,
            name=data.name,
            source_type=data.source_type,
            base_url=data.base_url,
            terms_allow_automation=data.terms_allow_automation,
            crawl_config=data.crawl_config,
        )
        await self.audit_repo.log(
            event_type="JOB_SOURCE_ADDED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="JobSource",
            entity_id=source.id,
            metadata={"name": data.name, "base_url": data.base_url},
        )
        return source

    async def update(
        self, candidate_id: UUID, user_id: UUID, source_id: UUID, data: JobSourceUpdate
    ) -> JobSource:
        source = await self.get(candidate_id, user_id, source_id)
        if data.base_url is not None:
            validate_source_url(data.base_url)
        update_payload = data.model_dump(exclude_unset=True)
        source = await self.repo.update(source, **update_payload)
        await self.audit_repo.log(
            event_type="JOB_SOURCE_UPDATED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="JobSource",
            entity_id=source.id,
        )
        return source

    async def delete(self, candidate_id: UUID, user_id: UUID, source_id: UUID) -> None:
        source = await self.get(candidate_id, user_id, source_id)
        await self.repo.delete(source)
        await self.audit_repo.log(
            event_type="JOB_SOURCE_DELETED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="JobSource",
            entity_id=source_id,
        )
