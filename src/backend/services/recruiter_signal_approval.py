"""CP19 human approval binding for recruiter signals.

Binds the human approval workflow to a candidate's persisted ``RecruiterSignal``
before anything (like outreach preparation) may consume it. Every review
request and decision is:

* candidate-scoped (ownership re-checked here and inside ``ApprovalService``),
* mapped to an ``Approval`` of kind ``recruiter_signal_review`` with the exact
  signal/evidence version linkage captured in its context (signal identity,
  evidence reference, generation version),
* driven by a human-attributable actor and timestamp (``ApprovalService``),
* mirrored to the append-only audit log on every transition.

No approval is ever issued automatically, and nothing here drafts or sends
outreach. A signal only ever transitions to ``APPROVED`` as the direct result
of a human APPROVE decision on its linked review approval.
"""

from __future__ import annotations

from uuid import UUID

from backend.core.exceptions import NotFoundError, ValidationError
from backend.models.approval import (
    Approval,
    ApprovalDecisionType,
    ApprovalKind,
    ApprovalStatus,
)
from backend.models.recruiter_signal import (
    RecruiterSignal,
    RecruiterSignalStatus,
    RecruiterSignalType,
)
from backend.repositories.approval import ApprovalDecisionRepository, ApprovalRepository
from backend.repositories.audit import AuditRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.company import CompanyRepository
from backend.repositories.job import JobRepository
from backend.repositories.recruiter_contact import RecruiterContactRepository
from backend.repositories.recruiter_signal import RecruiterSignalRepository
from backend.services.approval import ApprovalService
from backend.services.recruiter_signal import RecruiterSignalService

_REVIEWABLE_SIGNAL_TYPES = (RecruiterSignalType.RECRUITER_OUTREACH_CANDIDATE,)
_SIGNAL_TARGET_TYPE = "recruiter_signal"
_DECISIONS_APPLICABLE = frozenset(
    {
        ApprovalDecisionType.APPROVE,
        ApprovalDecisionType.REJECT,
        ApprovalDecisionType.CANCEL,
    }
)


class RecruiterSignalApprovalService:
    """Candidate-scoped human review of recruiter signals."""

    def __init__(
        self,
        *,
        signal_repo: RecruiterSignalRepository,
        contact_repo: RecruiterContactRepository,
        job_repo: JobRepository,
        company_repo: CompanyRepository,
        candidate_repo: CandidateRepository,
        approval_repo: ApprovalRepository,
        decision_repo: ApprovalDecisionRepository,
        audit_repo: AuditRepository,
    ) -> None:
        self._signals = signal_repo
        self._contacts = contact_repo
        self._jobs = job_repo
        self._companies = company_repo
        self._candidates = candidate_repo
        self._approvals = approval_repo
        self._decisions = decision_repo
        self._audit = audit_repo

    def _approval_service(self, *, user_id: UUID, candidate_id: UUID) -> ApprovalService:
        return ApprovalService(
            approval_repo=self._approvals,
            decision_repo=self._decisions,
            candidate_repo=self._candidates,
            audit_repo=self._audit,
            actor_id=user_id,
            candidate_id=candidate_id,
            autonomy_level=2,
            notifier=None,
        )

    def _signal_service(self, *, user_id: UUID, candidate_id: UUID) -> RecruiterSignalService:
        return RecruiterSignalService(
            signal_repo=self._signals,
            contact_repo=self._contacts,
            job_repo=self._jobs,
            company_repo=self._companies,
            candidate_repo=self._candidates,
            audit_repo=self._audit,
        )

    async def _owned_signal(
        self, candidate_id: UUID, signal_id: UUID
    ) -> RecruiterSignal:
        signal = await self._signals.get_for_candidate(signal_id, candidate_id)
        if signal is None:
            raise NotFoundError("Recruiter signal not found")
        return signal

    # ------------------------------------------------------------------ #
    # Review lifecycle
    # ------------------------------------------------------------------ #

    async def request_review(
        self,
        candidate_id: UUID,
        user_id: UUID,
        signal_id: UUID,
        *,
        summary: str | None = None,
    ) -> Approval:
        """Open a human review (``recruiter_signal_review``) for a signal.

        Idempotent: at most one open review approval exists per signal. The
        signal itself is untouched -- no status change, no automatic approval.
        """
        await self._candidates.get_for_user_or_404(candidate_id, user_id)
        signal = await self._owned_signal(candidate_id, signal_id)

        if signal.signal_type not in _REVIEWABLE_SIGNAL_TYPES:
            raise ValidationError(
                f"Signals of type {signal.signal_type.value} are not reviewable"
            )
        job = await self._jobs.get_for_candidate(signal.job_id, candidate_id)
        if job is None:
            raise NotFoundError("Job not found for signal")
        if signal.status in (
            RecruiterSignalStatus.APPROVED,
            RecruiterSignalStatus.REJECTED,
            RecruiterSignalStatus.EXPIRED,
        ):
            raise ValidationError(
                f"Signal is already {signal.status.value}; it cannot be re-reviewed"
            )

        linkage = self._linkage(signal)
        approval = await self._approval_service(
            user_id=user_id, candidate_id=candidate_id
        ).request_approval(
            kind=ApprovalKind.RECRUITER_SIGNAL_REVIEW,
            target_type=_SIGNAL_TARGET_TYPE,
            target_id=signal.id,
            summary=summary or f"Review recruiter outreach signal for {signal.signal_type.value}",
            context={
                **linkage,
                "job_id": str(signal.job_id),
                "recruiter_id": str(signal.recruiter_contact_id)
                if signal.recruiter_contact_id
                else None,
                "signal_status": signal.status.value,
                "signal_type": signal.signal_type.value,
            },
        )
        await self._audit.log(
            event_type="RECRUITER_SIGNAL_REVIEW_REQUESTED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="RecruiterSignal",
            entity_id=signal.id,
            metadata={
                "approval_id": str(approval.id),
                "review_kind": ApprovalKind.RECRUITER_SIGNAL_REVIEW.value,
                "summary": summary,
            },
        )
        return approval

    async def decide(
        self,
        candidate_id: UUID,
        user_id: UUID,
        approval_id: UUID,
        decision: ApprovalDecisionType,
        *,
        note: str | None = None,
    ) -> Approval:
        """Apply a human decision to a signal review; sync the signal state.

        APPROVE moves the signal to ``APPROVED`` (through ``READY_FOR_REVIEW``
        when needed). REJECT moves it to ``REJECTED``. CANCEL withdraws the
        request and leaves the signal as it was. Every decision is append-only,
        human-attributed, timestamped, and audited -- an approval is never
        issued automatically.
        """
        await self._candidates.get_for_user_or_404(candidate_id, user_id)
        approval = await self._approvals.get_for_candidate(approval_id, candidate_id)
        if approval is None:
            raise NotFoundError("Approval not found")
        if approval.kind is not ApprovalKind.RECRUITER_SIGNAL_REVIEW:
            raise ValidationError("Approval is not a recruiter-signal review")
        if approval.status not in (ApprovalStatus.PENDING, ApprovalStatus.SNOOZED):
            raise ValidationError(
                f"Approval is already {approval.status.value}; no further decisions allowed"
            )
        if decision not in _DECISIONS_APPLICABLE:
            raise ValidationError(
                f"Decision {decision.value} cannot be applied to a signal review"
            )

        signal_id = approval.target_id
        signal = await self._owned_signal(candidate_id, signal_id)

        approval_service = self._approval_service(user_id=user_id, candidate_id=candidate_id)
        updated = await approval_service.decide(approval_id, decision, note=note)

        if decision == ApprovalDecisionType.APPROVE:
            if signal.status in (
                RecruiterSignalStatus.DISCOVERED,
                RecruiterSignalStatus.EVIDENCE_PENDING,
            ):
                await self._signal_service(
                    user_id=user_id, candidate_id=candidate_id
                ).update_status(
                    candidate_id,
                    user_id,
                    signal.id,
                    RecruiterSignalStatus.READY_FOR_REVIEW,
                )
            await self._signal_service(
                user_id=user_id, candidate_id=candidate_id
            ).update_status(
                candidate_id,
                user_id,
                signal.id,
                RecruiterSignalStatus.APPROVED,
            )
        elif decision == ApprovalDecisionType.REJECT:
            await self._signal_service(
                user_id=user_id, candidate_id=candidate_id
            ).update_status(
                candidate_id,
                user_id,
                signal.id,
                RecruiterSignalStatus.REJECTED,
            )

        await self._audit.log(
            event_type="RECRUITER_SIGNAL_REVIEW_DECIDED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="RecruiterSignal",
            entity_id=signal.id,
            metadata={
                "approval_id": str(approval.id),
                "decision": decision.value,
                "signal_status": signal.status.value,
                "note": note,
            },
        )
        return updated

    # ------------------------------------------------------------------ #
    # Downstream gate (used by outreach preparation / sending)
    # ------------------------------------------------------------------ #

    async def require_approved_review(
        self,
        candidate_id: UUID,
        user_id: UUID,
        signal_id: UUID,
    ) -> Approval:
        """Return the approved human review for a signal, or raise.

        This is the gate callers must pass before consuming an approved signal
        (for example to prepare an outreach draft). It enforces that a human
        review truly approved the exact signal row.
        """
        await self._candidates.get_for_user_or_404(candidate_id, user_id)
        signal = await self._owned_signal(candidate_id, signal_id)
        approval = await self._approvals.get_approved_for_target(
            candidate_id,
            ApprovalKind.RECRUITER_SIGNAL_REVIEW,
            _SIGNAL_TARGET_TYPE,
            signal.id,
        )
        if approval is None:
            raise ValidationError(
                f"Signal {signal.id} has no approved human review; it cannot be consumed"
            )
        return approval

    # ------------------------------------------------------------------ #
    # Exact version linkage
    # ------------------------------------------------------------------ #

    @staticmethod
    def _linkage(signal: RecruiterSignal) -> dict[str, str | None]:
        provenance = signal.provenance_json or {}
        return {
            "signal_identity": signal.signal_identity,
            "evidence_reference": provenance.get("evidence_reference"),
            "generation_version": provenance.get("generation_version"),
            "signal_type": signal.signal_type.value,
        }


__all__ = [
    "RecruiterSignalApprovalService",
    "ApprovalKind",
]
