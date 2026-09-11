"""Job listing and detail service."""

from uuid import UUID

from backend.core.exceptions import NotFoundError
from backend.models.job import Job, JobStatus
from backend.repositories.candidate import CandidateRepository
from backend.repositories.job import JobRepository


class JobService:
    def __init__(
        self,
        repo: JobRepository,
        candidate_repo: CandidateRepository,
    ) -> None:
        self.repo = repo
        self.candidate_repo = candidate_repo

    async def list(
        self,
        candidate_id: UUID,
        user_id: UUID,
        *,
        status: JobStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Job]:
        await self.candidate_repo.get_for_user_or_404(candidate_id, user_id)
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        return await self.repo.list_for_candidate(candidate_id, status=status, limit=limit, offset=offset)

    async def get(self, candidate_id: UUID, user_id: UUID, job_id: UUID) -> Job:
        await self.candidate_repo.get_for_user_or_404(candidate_id, user_id)
        job = await self.repo.get_for_candidate(job_id, candidate_id)
        if job is None:
            raise NotFoundError("Job not found")
        return job
