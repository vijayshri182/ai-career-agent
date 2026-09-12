"""Human approval workflow service.

Enforces the safety invariant that external actions (application submission,
outreach send) cannot proceed without an explicit human decision. The service
is candidate-scoped: it guarantees the acting user owns the candidate and only
mutates approvals belonging to that candidate.
"""

from datetime import UTC, datetime
from uuid import UUID

from backend.core.exceptions import NotFoundError, ValidationError
from backend.models.approval import (
    Approval,
    ApprovalDecision,
    ApprovalDecisionType,
    ApprovalKind,
    ApprovalStatus,
)
from backend.repositories.approval import ApprovalDecisionRepository, ApprovalRepository
from backend.repositories.audit import AuditRepository
from backend.repositories.candidate import CandidateRepository

_TERMINAL = {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.CANCELLED}


class ApprovalService:
    def __init__(
        self,
        *,
        approval_repo: ApprovalRepository,
        decision_repo: ApprovalDecisionRepository,
        candidate_repo: CandidateRepository,
        audit_repo: AuditRepository,
        actor_id: UUID,
        candidate_id: UUID,
        autonomy_level: int = 2,
    ) -> None:
        self._approvals = approval_repo
        self._decisions = decision_repo
        self._candidates = candidate_repo
        self._audit = audit_repo
        self._actor_id = actor_id
        self._candidate_id = candidate_id
        self._autonomy_level = autonomy_level

    async def _ensure_owned_candidate(self) -> None:
        await self._candidates.get_for_user_or_404(self._candidate_id, self._actor_id)

    async def request_approval(
        self,
        *,
        kind: ApprovalKind,
        target_type: str,
        target_id: UUID,
        summary: str | None = None,
        context: dict[str, object] | None = None,
        application_id: UUID | None = None,
    ) -> Approval:
        """Create (or return the existing open) approval request for a target.

        Idempotent: at most one open (pending/snoozed) approval exists per
        (candidate, kind, target).
        """
        await self._ensure_owned_candidate()
        existing = await self._approvals.get_open_for_target(
            self._candidate_id, kind, target_type, target_id
        )
        if existing is not None:
            return existing
        approval = await self._approvals.create(
            candidate_id=self._candidate_id,
            kind=kind,
            status=ApprovalStatus.PENDING,
            target_type=target_type,
            target_id=target_id,
            application_id=application_id,
            autonomy_level=self._autonomy_level,
            summary=summary,
            context=context or {},
        )
        await self._audit.log(
            event_type="approval.requested",
            actor_id=self._actor_id,
            candidate_id=self._candidate_id,
            entity_type="approval",
            entity_id=approval.id,
            metadata={"kind": kind.value, "target_type": target_type, "target_id": str(target_id)},
        )
        return approval

    async def list_approvals(
        self,
        *,
        status: ApprovalStatus | None = None,
        kind: ApprovalKind | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Approval], int]:
        await self._ensure_owned_candidate()
        items = await self._approvals.list_for_candidate(
            self._candidate_id, status=status, kind=kind, limit=limit, offset=offset
        )
        total = await self._approvals.count_for_candidate(
            self._candidate_id, status=status, kind=kind
        )
        return items, total

    async def get_approval(self, approval_id: UUID, *, with_decisions: bool = False) -> Approval:
        await self._ensure_owned_candidate()
        if with_decisions:
            approval = await self._approvals.get_for_candidate_detailed(
                approval_id, self._candidate_id
            )
        else:
            approval = await self._approvals.get_for_candidate(approval_id, self._candidate_id)
        if approval is None:
            raise NotFoundError("Approval not found")
        return approval

    async def decide(
        self,
        approval_id: UUID,
        decision: ApprovalDecisionType,
        *,
        note: str | None = None,
        snoozed_until: datetime | None = None,
    ) -> Approval:
        """Apply a human decision to an open approval.

        Transitions: pending|snoozed -> approved, rejected, cancelled; snooze is
        only allowed from pending. Decisions are append-only and audited.
        """
        approval = await self.get_approval(approval_id)
        if approval.status not in (ApprovalStatus.PENDING, ApprovalStatus.SNOOZED):
            raise ValidationError(
                f"Approval is already {approval.status.value}; no further decisions "
                f"({decision.value}) are allowed"
            )
        if decision == ApprovalDecisionType.SNOOZE:
            if approval.status != ApprovalStatus.PENDING:
                raise ValidationError("Only a pending approval can be snoozed")
            if snoozed_until is None:
                raise ValidationError("Snooze requires an 'until' timestamp")
            if snoozed_until <= datetime.now(UTC):
                raise ValidationError("Snooze 'until' must be in the future")
            new_status = ApprovalStatus.SNOOZED
        elif decision == ApprovalDecisionType.APPROVE:
            new_status = ApprovalStatus.APPROVED
        elif decision == ApprovalDecisionType.REJECT:
            new_status = ApprovalStatus.REJECTED
        elif decision == ApprovalDecisionType.CANCEL:
            new_status = ApprovalStatus.CANCELLED
        else:
            raise ValidationError(f"Decision {decision.value} cannot be applied here")

        updated = await self._approvals.update(
            approval,
            status=new_status,
            decided_by=str(self._actor_id),
            decided_at=datetime.now(UTC),
            decision_type=decision,
            decision_note=note,
            snoozed_until=snoozed_until if decision == ApprovalDecisionType.SNOOZE else None,
        )
        await self._decisions.create(
            approval_id=approval.id,
            actor_id=str(self._actor_id),
            decision_type=decision,
            note=note,
        )
        await self._audit.log(
            event_type=f"approval.{decision.value}",
            actor_id=self._actor_id,
            candidate_id=self._candidate_id,
            entity_type="approval",
            entity_id=approval.id,
            metadata={"status": new_status.value, "note": note} if note else {"status": new_status.value},
        )
        return updated

    async def list_decisions(self, approval_id: UUID) -> list[ApprovalDecision]:
        await self.get_approval(approval_id)
        return await self._decisions.list_for_approval(approval_id)
