"""Human-in-the-loop workflow state machine and service.

A WorkflowRun starts RUNNING. When a site presents a challenge that requires a
human, the workflow pauses (PAUSED_HUMAN_ACTION). It may only be resumed with a
matching opaque token, from the paused state, before expiry, and while the
attempt budget allows it. Repeated resumes without a new resolution are capped,
so an unresolved challenge can never cause an endless retry loop. All other
transitions lead to a terminal state (COMPLETED, CANCELLED, TIMED_OUT, FAILED).
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from backend.core.exceptions import NotFoundError, ValidationError
from backend.models.workflow_run import WorkflowRun, WorkflowStatus
from backend.repositories.audit import AuditRepository
from backend.repositories.workflow_run import WorkflowRunRepository

_TERMINAL_WORKFLOW_STATES: frozenset[WorkflowStatus] = frozenset(
    {
        WorkflowStatus.COMPLETED,
        WorkflowStatus.CANCELLED,
        WorkflowStatus.TIMED_OUT,
        WorkflowStatus.FAILED,
    }
)


class WorkflowStateMachine:
    """Pure transition rules for WorkflowStatus."""

    TERMINAL_STATES: frozenset[WorkflowStatus] = _TERMINAL_WORKFLOW_STATES

    TRANSITIONS: dict[WorkflowStatus, frozenset[WorkflowStatus]] = {
        WorkflowStatus.RUNNING: frozenset(
            {
                WorkflowStatus.PAUSED_HUMAN_ACTION,
                WorkflowStatus.COMPLETED,
                WorkflowStatus.CANCELLED,
                WorkflowStatus.TIMED_OUT,
                WorkflowStatus.FAILED,
            }
        ),
        WorkflowStatus.PAUSED_HUMAN_ACTION: frozenset(
            _TERMINAL_WORKFLOW_STATES | {WorkflowStatus.RUNNING} | {WorkflowStatus.RESUMED}
        ),
        WorkflowStatus.RESUMED: frozenset(_TERMINAL_WORKFLOW_STATES),
        WorkflowStatus.COMPLETED: frozenset(),
        WorkflowStatus.CANCELLED: frozenset(),
        WorkflowStatus.TIMED_OUT: frozenset(),
        WorkflowStatus.FAILED: frozenset(),
    }

    @staticmethod
    def can_transition(current: WorkflowStatus, target: WorkflowStatus) -> bool:
        return target in WorkflowStateMachine.TRANSITIONS.get(current, frozenset())

    @staticmethod
    def transition(current: WorkflowStatus, target: WorkflowStatus) -> WorkflowStatus:
        if not WorkflowStateMachine.can_transition(current, target):
            raise ValidationError(
                f"Illegal workflow state transition: {current.value} -> {target.value}"
            )
        return target

    @staticmethod
    def is_terminal(status: WorkflowStatus) -> bool:
        return status in WorkflowStateMachine.TERMINAL_STATES


class HumanInTheLoopService:
    def __init__(
        self,
        repo: WorkflowRunRepository,
        audit_repo: AuditRepository,
        actor_id: UUID,
        candidate_id: UUID,
    ) -> None:
        self.repo = repo
        self.audit_repo = audit_repo
        self.actor_id = actor_id
        self.candidate_id = candidate_id

    async def start(
        self,
        provider_id: UUID,
        workflow_type: str = "authentication_and_challenge",
        context: dict[str, object] | None = None,
        max_attempts: int = 2,
        expires_in_seconds: int | None = None,
    ) -> WorkflowRun:
        now = datetime.now(UTC)
        run = await self.repo.create(
            candidate_id=self.candidate_id,
            provider_id=provider_id,
            workflow_type=workflow_type,
            status=WorkflowStatus.RUNNING,
            attempt_count=0,
            max_attempts=max_attempts,
            context_metadata=context or {},
            started_at=now,
            expires_at=(now + timedelta(seconds=expires_in_seconds)) if expires_in_seconds else None,
        )
        await self.audit_repo.log(
            event_type="WORKFLOW_STARTED",
            actor_id=self.actor_id,
            candidate_id=self.candidate_id,
            entity_type="WorkflowRun",
            entity_id=run.id,
            metadata={"provider_id": str(provider_id), "workflow_type": workflow_type},
        )
        return run

    async def pause_for_human_action(self, run: WorkflowRun) -> WorkflowRun:
        if WorkflowStateMachine.is_terminal(run.status):
            return run
        target = await self._apply_and_update(run, WorkflowStatus.PAUSED_HUMAN_ACTION)
        run.paused_at = datetime.now(UTC)
        await self.repo.update(run)
        await self.audit_repo.log(
            event_type="WORKFLOW_PAUSED",
            actor_id=self.actor_id,
            candidate_id=self.candidate_id,
            entity_type="WorkflowRun",
            entity_id=run.id,
            result="human_action",
            metadata={"provider_id": str(run.provider_id)},
        )
        return target

    async def resume(self, run: WorkflowRun, token: UUID | None = None) -> WorkflowRun:
        """Idempotently resume a paused workflow if the token matches, before
        expiry, and while the attempt budget remains.
        """
        if run.status == WorkflowStatus.RUNNING:
            return run
        if WorkflowStateMachine.is_terminal(run.status):
            raise ValidationError(f"Workflow is already {run.status.value}")
        if run.status not in (WorkflowStatus.PAUSED_HUMAN_ACTION, WorkflowStatus.RESUMED):
            raise ValidationError(f"Cannot resume workflow in state {run.status.value}")
        if token is None or token != run.resume_token:
            raise ValidationError("Invalid resume token")
        if self._expired(run):
            await self.mark_timed_out(run)
            raise ValidationError("Workflow expired before it could be resumed")
        if run.attempt_count >= run.max_attempts:
            await self.mark_failed(
                run, reason="Maximum resume attempts exceeded without resolution"
            )
            raise ValidationError(
                "Maximum resume attempts exceeded; workflow failed until a new human action"
            )

        run.attempt_count = run.attempt_count + 1
        run.resumed_at = datetime.now(UTC)
        target = await self._apply_and_update(run, WorkflowStatus.RUNNING)
        await self.audit_repo.log(
            event_type="WORKFLOW_RESUMED",
            actor_id=self.actor_id,
            candidate_id=self.candidate_id,
            entity_type="WorkflowRun",
            entity_id=run.id,
            metadata={"attempt_count": run.attempt_count, "provider_id": str(run.provider_id)},
        )
        return target

    async def mark_completed(self, run: WorkflowRun) -> WorkflowRun:
        target = await self._apply_and_update(run, WorkflowStatus.COMPLETED)
        return await self._finish(run, target, "WORKFLOW_COMPLETED")

    async def cancel(self, run: WorkflowRun, reason: str | None = None) -> WorkflowRun:
        target = await self._apply_and_update(run, WorkflowStatus.CANCELLED)
        return await self._finish(
            run, target, "WORKFLOW_CANCELLED", metadata={"reason": reason or "cancelled_by_user"}
        )

    async def mark_timed_out(self, run: WorkflowRun) -> WorkflowRun:
        target = await self._apply_and_update(run, WorkflowStatus.TIMED_OUT)
        return await self._finish(run, target, "WORKFLOW_TIMED_OUT")

    async def mark_failed(self, run: WorkflowRun, reason: str | None = None) -> WorkflowRun:
        target = await self._apply_and_update(run, WorkflowStatus.FAILED)
        return await self._finish(
            run, target, "WORKFLOW_FAILED", metadata={"reason": reason or "terminal_failure"}
        )

    async def get_or_404(self, run_id: UUID) -> WorkflowRun:
        return await self.repo.get_for_candidate_or_404(run_id, self.candidate_id)

    async def latest_for_provider(self, provider_id: UUID) -> WorkflowRun | None:
        run = await self.repo.latest_for_provider(provider_id)
        if run is None or run.candidate_id != self.candidate_id:
            raise NotFoundError("Workflow not found")
        return run

    async def list(self, status: WorkflowStatus | None = None) -> list[WorkflowRun]:
        return await self.repo.list_by_candidate(self.candidate_id, status=status)

    def _expired(self, run: WorkflowRun) -> bool:
        if run.expires_at is None:
            return False
        expires_at = run.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return datetime.now(UTC) > expires_at

    async def _apply_and_update(self, run: WorkflowRun, target: WorkflowStatus) -> WorkflowRun:
        WorkflowStateMachine.transition(run.status, target)
        run.status = target
        await self.repo.update(run)
        return run

    async def _finish(
        self,
        run: WorkflowRun,
        target: WorkflowRun,
        event_type: str,
        metadata: dict[str, object] | None = None,
    ) -> WorkflowRun:
        run.finished_at = datetime.now(UTC)
        await self.audit_repo.log(
            event_type=event_type,
            actor_id=self.actor_id,
            candidate_id=self.candidate_id,
            entity_type="WorkflowRun",
            entity_id=run.id,
            metadata={"status": run.status.value, **(metadata or {})},
        )
        return target
