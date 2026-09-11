"""Challenge schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.models.challenge import (
    ChallengeResolution,
    ChallengeSeverity,
    ChallengeStatus,
    ChallengeType,
)


class ChallengeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    provider_id: UUID
    workflow_id: UUID | None
    challenge_type: ChallengeType
    status: ChallengeStatus
    severity: ChallengeSeverity
    human_required: bool
    description: str | None
    context_metadata: dict[str, object]
    detected_at: datetime
    acknowledged_at: datetime | None
    expires_at: datetime | None
    resolved_at: datetime | None
    cancelled_at: datetime | None
    timed_out_at: datetime | None
    resolution_method: ChallengeResolution | None
    retry_count: int
    max_retries: int


class ChallengeAcknowledgeInput(BaseModel):
    pass


class ChallengeCompleteInput(BaseModel):
    resolution_method: ChallengeResolution = ChallengeResolution.HUMAN
    notes: str | None = None


class ChallengeCancelInput(BaseModel):
    reason: str | None = None
