"""Application submission adapters.

Defines the pluggable :class:`ApplicationSubmitter` protocol and a safe
recording default. No real ATS interaction happens here; real browser/API ATS
fillers plug in behind the same protocol and MUST reuse the policy gate and
challenge hand-off behaviour in :mod:`backend.services.application_automation`.

The default submitter only records that an explicit-permission ATS accepted the
application: the ``AutomationRun`` row plus the audit trail already form a
durable submission record, which keeps development and tests deterministic and
safe.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol
from uuid import UUID

from backend.models.challenge import ChallengeType


class SubmitOutcomeKind(str, Enum):
    """How an adapter completed one submit attempt."""

    SUBMITTED = "submitted"
    CHALLENGE = "challenge"
    FAILED = "failed"


@dataclass
class SubmissionPayload:
    """Non-secret material an adapter needs to perform a submission."""

    application_id: UUID
    job_url: str
    job_title: str
    company_name: str
    source_site: str | None = None
    resume_id: UUID | None = None
    documents: list[str] = field(default_factory=list)


@dataclass
class SubmitOutcome:
    """Result of a single submit attempt (no secrets, no tokens)."""

    kind: SubmitOutcomeKind
    message: str = ""
    retryable: bool = True
    challenge_type: ChallengeType | None = None
    details: dict[str, object] | None = None


class ApplicationSubmitter(Protocol):
    async def submit(self, payload: SubmissionPayload) -> SubmitOutcome:
        """Perform (or simulate) one submission attempt."""


class RecordingSubmitter:
    """Default submitter: records a successful submission for a permitted ATS.

    Suitable for development, tests, and as a safe baseline when credentials
    are not configured. It performs no network or browser automation.
    """

    async def submit(self, payload: SubmissionPayload) -> SubmitOutcome:
        return SubmitOutcome(
            kind=SubmitOutcomeKind.SUBMITTED,
            message="Submission recorded (automation permitted by source)",
            details={
                "application_id": str(payload.application_id),
                "job_url": payload.job_url,
                "company": payload.company_name,
                "documents": payload.documents,
                "mode": "recording",
            },
        )


def make_submitter() -> ApplicationSubmitter:
    """Build the default submitter (injectable for tests and adapters)."""
    return RecordingSubmitter()
