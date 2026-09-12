"""Unit tests for the approval workflow service (state machine + ownership)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import NotFoundError, ValidationError
from backend.models.approval import (
    ApprovalDecisionType,
    ApprovalKind,
    ApprovalStatus,
)
from backend.services.approval import ApprovalService


def _build_service(session: AsyncSession, candidate, user) -> ApprovalService:
    from backend.repositories.approval import ApprovalDecisionRepository, ApprovalRepository
    from backend.repositories.audit import AuditRepository
    from backend.repositories.candidate import CandidateRepository

    return ApprovalService(
        approval_repo=ApprovalRepository(session),
        decision_repo=ApprovalDecisionRepository(session),
        candidate_repo=CandidateRepository(session),
        audit_repo=AuditRepository(session),
        actor_id=user.id,
        candidate_id=candidate.id,
        autonomy_level=2,
    )


async def test_request_creates_pending_approval(
    session: AsyncSession, candidate, test_user
):
    service = _build_service(session, candidate, test_user)
    target = uuid4()
    approval = await service.request_approval(
        kind=ApprovalKind.APPLICATION_SUBMISSION,
        target_type="application",
        target_id=target,
        summary="Submit prepared application",
        context={"match_score": 82.0},
    )
    assert approval.status == ApprovalStatus.PENDING
    assert approval.target_id == target
    assert approval.autonomy_level == 2
    await session.commit()


async def test_request_is_idempotent(session: AsyncSession, candidate, test_user):
    service = _build_service(session, candidate, test_user)
    target = uuid4()
    first = await service.request_approval(
        kind=ApprovalKind.APPLICATION_SUBMISSION, target_type="application", target_id=target
    )
    second = await service.request_approval(
        kind=ApprovalKind.APPLICATION_SUBMISSION, target_type="application", target_id=target
    )
    assert first.id == second.id
    await session.commit()


async def test_approve_then_no_further_decision(
    session: AsyncSession, candidate, test_user
):
    service = _build_service(session, candidate, test_user)
    approval = await service.request_approval(
        kind=ApprovalKind.APPLICATION_SUBMISSION, target_type="application", target_id=uuid4()
    )
    approved = await service.decide(
        approval.id, ApprovalDecisionType.APPROVE, note="Good to go"
    )
    assert approved.status == ApprovalStatus.APPROVED
    assert approved.decision_type == ApprovalDecisionType.APPROVE
    assert approved.decided_by == str(test_user.id)
    with pytest.raises(ValidationError):
        await service.decide(approval.id, ApprovalDecisionType.REJECT)
    await session.commit()


async def test_snooze_requires_future_and_only_from_pending(
    session: AsyncSession, candidate, test_user
):
    service = _build_service(session, candidate, test_user)
    approval = await service.request_approval(
        kind=ApprovalKind.APPLICATION_SUBMISSION, target_type="application", target_id=uuid4()
    )
    with pytest.raises(ValidationError):
        await service.decide(
            approval.id,
            ApprovalDecisionType.SNOOZE,
            snoozed_until=datetime.now(UTC) - timedelta(days=1),
        )
    snoozed = await service.decide(
        approval.id,
        ApprovalDecisionType.SNOOZE,
        snoozed_until=datetime.now(UTC) + timedelta(days=3),
        note="Later",
    )
    assert snoozed.status == ApprovalStatus.SNOOZED
    # Snoozed approvals may still be rejected.
    rejected = await service.decide(approval.id, ApprovalDecisionType.REJECT)
    assert rejected.status == ApprovalStatus.REJECTED
    await session.commit()


async def test_reject_and_cancel_transitions(
    session: AsyncSession, candidate, test_user
):
    service = _build_service(session, candidate, test_user)
    approval = await service.request_approval(
        kind=ApprovalKind.OUTREACH_SEND, target_type="outreach", target_id=uuid4()
    )
    cancelled = await service.decide(approval.id, ApprovalDecisionType.CANCEL)
    assert cancelled.status == ApprovalStatus.CANCELLED
    with pytest.raises(ValidationError):
        await service.decide(approval.id, ApprovalDecisionType.APPROVE)
    await session.commit()


async def test_cross_candidate_lookup_is_hidden(session: AsyncSession, candidate, test_user):
    from backend.repositories.approval import ApprovalRepository

    service = _build_service(session, candidate, test_user)
    approval = await service.request_approval(
        kind=ApprovalKind.APPLICATION_SUBMISSION, target_type="application", target_id=uuid4()
    )
    # Approval belongs to this candidate; a different candidate must not see it.
    repo = ApprovalRepository(session)
    other = await repo.get_for_candidate(approval.id, uuid4())
    assert other is None


async def test_get_unknown_approval_404(session: AsyncSession, candidate, test_user):
    service = _build_service(session, candidate, test_user)
    with pytest.raises(NotFoundError):
        await service.get_approval(uuid4())


async def test_decisions_are_recorded(
    session: AsyncSession, candidate, test_user
):
    service = _build_service(session, candidate, test_user)
    approval = await service.request_approval(
        kind=ApprovalKind.APPLICATION_SUBMISSION, target_type="application", target_id=uuid4()
    )
    await service.decide(approval.id, ApprovalDecisionType.APPROVE, note="yes")
    decisions = await service.list_decisions(approval.id)
    assert len(decisions) == 1
    assert decisions[0].decision_type == ApprovalDecisionType.APPROVE
    assert decisions[0].actor_id == str(test_user.id)
    await session.commit()


async def test_list_filters_by_status(
    session: AsyncSession, candidate, test_user
):
    service = _build_service(session, candidate, test_user)
    a = await service.request_approval(
        kind=ApprovalKind.APPLICATION_SUBMISSION, target_type="application", target_id=uuid4()
    )
    await service.decide(a.id, ApprovalDecisionType.APPROVE)
    await service.request_approval(
        kind=ApprovalKind.OUTREACH_SEND, target_type="outreach", target_id=uuid4()
    )
    all_items, total = await service.list_approvals()
    assert total == 2
    pending, pending_total = await service.list_approvals(status=ApprovalStatus.PENDING)
    assert pending_total == 1
    assert pending[0].kind == ApprovalKind.OUTREACH_SEND
    approved, approved_total = await service.list_approvals(status=ApprovalStatus.APPROVED)
    assert approved_total == 1
    outreach, outreach_total = await service.list_approvals(kind=ApprovalKind.OUTREACH_SEND)
    assert outreach_total == 1
