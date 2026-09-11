"""Challenge service.

Runs the challenge lifecycle and keeps the linked human-in-the-loop workflow in
sync. All operations are idempotent where it matters:
- detecting the same challenge twice reuses the in-flight challenge;
- acknowledging/completing an item already handled is a safe no-op;
- resolving via completion or supersession resumes the (already paused) workflow
  exactly once and always after the challenge is actually resolved.

No secrets are accepted or stored anywhere in this module.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from backend.core.exceptions import ValidationError
from backend.models.authentication import AuthProvider, AuthState
from backend.models.challenge import (
    Challenge,
    ChallengeResolution,
    ChallengeSeverity,
    ChallengeStatus,
    ChallengeType,
)
from backend.models.workflow_run import WorkflowStatus
from backend.repositories.audit import AuditRepository
from backend.repositories.challenge import ChallengeRepository
from backend.services.authentication_provider import AuthProviderService
from backend.services.human_in_loop import HumanInTheLoopService

TERMINAL_STATUSES = frozenset(
    {
        ChallengeStatus.RESOLVED,
        ChallengeStatus.CANCELLED,
        ChallengeStatus.TIMED_OUT,
        ChallengeStatus.FAILED,
    }
)


async def _finish_workflow_after_resolution(
    workflow_service: HumanInTheLoopService, run_id: UUID | None
) -> None:
    """Resume a paused workflow, or complete one that never paused."""
    if run_id is None:
        return
    run = await workflow_service.get_or_404(UUID(str(run_id)))
    if run.status == WorkflowStatus.RUNNING:
        await workflow_service.mark_completed(run)
    else:
        await workflow_service.resume(run, run.resume_token)


class ChallengeService:
    def __init__(
        self,
        repo: ChallengeRepository,
        audit_repo: AuditRepository,
        provider_service: AuthProviderService,
        workflow_service: HumanInTheLoopService,
        actor_id: UUID,
        candidate_id: UUID,
    ) -> None:
        self.repo = repo
        self.audit_repo = audit_repo
        self.provider_service = provider_service
        self.workflow_service = workflow_service
        self.actor_id = actor_id
        self.candidate_id = candidate_id

    async def ensure_open(
        self,
        provider: AuthProvider,
        challenge_type: ChallengeType,
        description: str | None = None,
        metadata: dict[str, object] | None = None,
        human_required: bool = True,
        severity: ChallengeSeverity = ChallengeSeverity.MEDIUM,
        expires_in_seconds: int = 60 * 60 * 24,
        max_retries: int = 2,
    ) -> Challenge:
        """Detect/record a challenge. Idempotent: reuses the in-flight
        challenge of the same type for the provider instead of duplicating.
        """
        existing = await self.repo.get_in_flight(provider.id, challenge_type)
        if existing is not None:
            return existing

        workflow = await self.workflow_service.start(
            provider_id=provider.id,
            context={"challenge_type": challenge_type.value},
            max_attempts=max_retries + 1,
            expires_in_seconds=expires_in_seconds,
        )
        if human_required:
            workflow = await self.workflow_service.pause_for_human_action(workflow)

        challenge = await self.repo.create(
            candidate_id=self.candidate_id,
            provider_id=provider.id,
            workflow_id=str(workflow.id),
            challenge_type=challenge_type,
            status=ChallengeStatus.OPEN,
            severity=severity,
            human_required=human_required,
            description=description,
            context_metadata=metadata or {},
            detected_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in_seconds),
            retry_count=0,
            max_retries=max_retries,
        )
        await self.audit_repo.log(
            event_type="CHALLENGE_DETECTED",
            actor_id=self.actor_id,
            candidate_id=self.candidate_id,
            entity_type="Challenge",
            entity_id=challenge.id,
            metadata={
                "provider_id": str(provider.id),
                "challenge_type": challenge_type.value,
                "human_required": human_required,
                "severity": severity.value,
            },
            details=description,
        )
        await self.audit_repo.log(
            event_type="HUMAN_ACTION_REQUESTED",
            actor_id=self.actor_id,
            candidate_id=self.candidate_id,
            entity_type="Challenge",
            entity_id=challenge.id,
            result="pending" if human_required else "not_required",
            metadata={"challenge_type": challenge_type.value, "human_required": human_required},
        )
        return challenge

    async def escalate(self, challenge: Challenge) -> Challenge:
        """Mark a challenge as explicitly requiring a human, pausing the
        workflow first. Idempotent once already escalated.
        """
        if challenge.status == ChallengeStatus.HUMAN_ACTION_REQUIRED:
            return challenge
        self._assert_in_flight(challenge)
        challenge.status = ChallengeStatus.HUMAN_ACTION_REQUIRED
        await self.repo.update(challenge)
        run = None
        if challenge.workflow_id is not None:
            run = await self.workflow_service.get_or_404(UUID(str(challenge.workflow_id)))
        if run is not None:
            await self.workflow_service.pause_for_human_action(run)
        await self.audit_repo.log(
            event_type="HUMAN_ACTION_REQUIRED",
            actor_id=self.actor_id,
            candidate_id=self.candidate_id,
            entity_type="Challenge",
            entity_id=challenge.id,
            metadata={"challenge_type": challenge.challenge_type.value},
        )
        return challenge

    async def acknowledge(self, challenge: Challenge) -> Challenge:
        if challenge.status == ChallengeStatus.ACKNOWLEDGED:
            return challenge
        self._assert_in_flight(challenge)
        challenge.status = ChallengeStatus.ACKNOWLEDGED
        challenge.acknowledged_at = datetime.now(UTC)
        await self.repo.update(challenge)
        await self.audit_repo.log(
            event_type="CHALLENGE_ACKNOWLEDGED",
            actor_id=self.actor_id,
            candidate_id=self.candidate_id,
            entity_type="Challenge",
            entity_id=challenge.id,
            metadata={"challenge_type": challenge.challenge_type.value},
        )
        return challenge

    async def complete(
        self,
        challenge: Challenge,
        resolution_method: ChallengeResolution = ChallengeResolution.HUMAN,
        notes: str | None = None,
    ) -> Challenge:
        """Mark a challenge resolved. Only safe after the human actually
        completed the site's flow (or the challenge was superseded by a new
        authenticated session). Resumes the paused workflow once.
        """
        self._assert_in_flight(challenge)
        if challenge.status == ChallengeStatus.OPEN:
            challenge = await self.acknowledge(challenge)
        challenge.status = ChallengeStatus.RESOLVED
        challenge.resolution_method = resolution_method
        challenge.resolved_at = datetime.now(UTC)
        if notes:
            challenge.context_metadata = {
                **(challenge.context_metadata or {}),
                "resolution_notes": notes,
            }
        await self.repo.update(challenge)

        provider = await self.provider_service.get(challenge.provider_id)
        await self._set_authenticated(provider)
        await _finish_workflow_after_resolution(self.workflow_service, challenge.workflow_id)

        await self.audit_repo.log(
            event_type="CHALLENGE_COMPLETED",
            actor_id=self.actor_id,
            candidate_id=self.candidate_id,
            entity_type="Challenge",
            entity_id=challenge.id,
            metadata={
                "challenge_type": challenge.challenge_type.value,
                "resolution_method": resolution_method.value,
            },
        )
        return challenge

    async def cancel(self, challenge: Challenge, reason: str | None = None) -> Challenge:
        self._assert_in_flight(challenge)
        challenge.status = ChallengeStatus.CANCELLED
        challenge.cancelled_at = datetime.now(UTC)
        await self.repo.update(challenge)
        run = None
        if challenge.workflow_id is not None:
            run = await self.workflow_service.get_or_404(UUID(str(challenge.workflow_id)))
        if run is not None:
            await self.workflow_service.cancel(run, reason=reason or "challenge_cancelled")
        await self.audit_repo.log(
            event_type="CHALLENGE_CANCELLED",
            actor_id=self.actor_id,
            candidate_id=self.candidate_id,
            entity_type="Challenge",
            entity_id=challenge.id,
            metadata={"challenge_type": challenge.challenge_type.value, "reason": reason},
        )
        return challenge

    async def time_out(self, challenge: Challenge) -> Challenge:
        self._assert_in_flight(challenge)
        challenge.status = ChallengeStatus.TIMED_OUT
        challenge.timed_out_at = datetime.now(UTC)
        await self.repo.update(challenge)
        run = None
        if challenge.workflow_id is not None:
            run = await self.workflow_service.get_or_404(UUID(str(challenge.workflow_id)))
        if run is not None:
            await self.workflow_service.mark_timed_out(run)
        await self.audit_repo.log(
            event_type="CHALLENGE_TIMED_OUT",
            actor_id=self.actor_id,
            candidate_id=self.candidate_id,
            entity_type="Challenge",
            entity_id=challenge.id,
            metadata={"challenge_type": challenge.challenge_type.value},
        )
        return challenge

    async def resolve_superseded(self, provider: AuthProvider) -> list[Challenge]:
        """When a session becomes authenticated again, close any in-flight
        challenges as SUPERSEDED and resume their workflows (idempotent).
        """
        resolved: list[Challenge] = []
        for challenge in await self.repo.list_in_flight_by_provider(provider.id):
            challenge.status = ChallengeStatus.RESOLVED
            challenge.resolution_method = ChallengeResolution.SUPERSEDED
            challenge.resolved_at = datetime.now(UTC)
            await self.repo.update(challenge)
            await _finish_workflow_after_resolution(self.workflow_service, challenge.workflow_id)
            await self.audit_repo.log(
                event_type="CHALLENGE_RESOLVED_SUPERSEDED",
                actor_id=self.actor_id,
                candidate_id=self.candidate_id,
                entity_type="Challenge",
                entity_id=challenge.id,
                metadata={"challenge_type": challenge.challenge_type.value},
            )
            resolved.append(challenge)
        return resolved

    async def list(
        self, status: ChallengeStatus | None = None, open_only: bool = False
    ) -> list[Challenge]:
        if open_only:
            return await self.repo.list_open_by_candidate(self.candidate_id)
        return await self.repo.list_by_candidate(self.candidate_id, status=status)

    async def get(self, challenge_id: UUID) -> Challenge:
        return await self.repo.get_for_candidate_or_404(challenge_id, self.candidate_id)

    async def _set_authenticated(self, provider: AuthProvider) -> None:
        state = await self.provider_service.get_state(provider.id)
        if state.status != AuthState.AUTHENTICATED:
            await self.provider_service.apply_state(provider, AuthState.AUTHENTICATED)

    def _assert_in_flight(self, challenge: Challenge) -> None:
        if challenge.status in TERMINAL_STATUSES:
            raise ValidationError(f"Challenge is already {challenge.status.value}")
