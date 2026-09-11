"""Job discovery schemas."""

from uuid import UUID

from pydantic import BaseModel, Field

from backend.schemas.agent_task import AgentTaskRead


class DiscoveryRunRequest(BaseModel):
    """Optional scoping for a discovery run.

    When `source_ids` is omitted or empty, every enabled source for the
    candidate is crawled.
    """

    source_ids: list[UUID] = Field(default_factory=list)


class SourceRunOutcome(BaseModel):
    source_id: UUID
    source_name: str
    ok: bool
    jobs_fetched: int = 0
    new_jobs: int = 0
    duplicate_jobs: int = 0
    extracted: int = 0
    error: str | None = None


class DiscoveryRunResult(BaseModel):
    task: AgentTaskRead
    candidate_id: UUID
    sources_attempted: int
    sources_succeeded: int
    fetched: int = 0
    new_jobs: int = 0
    duplicate_jobs: int = 0
    marked_expired: int = 0
    source_outcomes: list[SourceRunOutcome] = Field(default_factory=list)
