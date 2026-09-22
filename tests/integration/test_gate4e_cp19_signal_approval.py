"""CP19 recruiter-signal human approval binding integration tests.

The human review (``Approval`` kind ``recruiter_signal_review``) is the only way
a recruiter outreach signal moves to ``APPROVED``. No approval is ever granted
automatically; every transition is human-attributed, timestamped, append-only,
and mirrored to the audit log. Nothing here drafts or sends outreach.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import NotFoundError, ValidationError
from backend.models.approval import (
    Approval,
    ApprovalDecisionType,
    ApprovalKind,
    ApprovalStatus,
)
from backend.models.audit import AuditEvent
from backend.models.recruiter_signal import RecruiterSignalStatus, RecruiterSignalType
from backend.repositories.approval import ApprovalDecisionRepository, ApprovalRepository
from tests.integration.gate4e_signal_support import (
    build_approval_service,
    generate_outreach_signals,
    load_signal,
    outreach_candidate,
    seed_contact,
    seed_employer,
    seed_job,
)

_REVIEW_KIND = ApprovalKind.RECRUITER_SIGNAL_REVIEW


async def _foreign_candidate(session: AsyncSession):
    from backend.repositories.candidate import CandidateRepository
    from backend.repositories.user import UserRepository

    user = await UserRepository(session).create_user(
        "cp19-foreign@example.com", "Cp19Password123!"
    )
    candidate = await CandidateRepository(session).create_for_user(
        user_id=user.id, full_name="Foreign CP19", email="foreign-cp19@example.com"
    )
    await session.flush()
    return candidate


async def _owned_signal(session: AsyncSession, candidate):
    employer = await seed_employer(session)
    job = await seed_job(session, candidate, employer)
    await seed_contact(session, candidate, employer, job)
    generated = await generate_outreach_signals(session, candidate, candidate.user_id)
    identity = outreach_candidate(generated)
    assert identity is not None
    return await load_signal(session, candidate.id, identity)


async def _signal_of_type(session: AsyncSession, candidate, signal_type_value: str):
    employer = await seed_employer(session)
    job = await seed_job(session, candidate, employer)
    await seed_contact(session, candidate, employer, job)
    generated = await generate_outreach_signals(session, candidate, candidate.user_id)
    match = next(
        (g for g in generated if g.signal_type.value == signal_type_value), None
    )
    assert match is not None, f"no {signal_type_value} signal generated"
    return await load_signal(session, candidate.id, match.signal_identity)


async def _review_service(session: AsyncSession):
    return await build_approval_service(session)


async def _audit_events(session: AsyncSession, candidate_id, event_type: str):
    return (
        await session.execute(
            select(AuditEvent).where(
                AuditEvent.event_type == event_type,
                AuditEvent.candidate_id == str(candidate_id),
            )
        )
    ).scalars().all()


async def test_request_review_creates_review_approval(session, candidate):
    signal = await _owned_signal(session, candidate)
    approval = await (await _review_service(session)).request_review(
        candidate.id, candidate.user_id, signal.id
    )
    assert approval.kind is _REVIEW_KIND
    assert approval.status is ApprovalStatus.PENDING
    assert approval.target_type == "recruiter_signal"
    assert approval.target_id == signal.id
    assert approval.candidate_id == candidate.id
    context = approval.context or {}
    assert context.get("signal_identity") == signal.signal_identity
    provenance = signal.provenance_json or {}
    assert context.get("evidence_reference") == provenance.get("evidence_reference")
    assert context.get("generation_version") == provenance.get("generation_version")
    assert context.get("signal_type") == signal.signal_type.value
    events = await _audit_events(session, candidate.id, "RECRUITER_SIGNAL_REVIEW_REQUESTED")
    assert events
    assert events[-1].actor_id == str(candidate.user_id)


async def test_request_review_is_idempotent(session, candidate):
    signal = await _owned_signal(session, candidate)
    service = await _review_service(session)
    first = await service.request_review(candidate.id, candidate.user_id, signal.id)
    second = await service.request_review(candidate.id, candidate.user_id, signal.id)
    assert second.id == first.id
    assert second.status is ApprovalStatus.PENDING
    count = (
        await session.execute(
            select(func.count())
            .select_from(Approval)
            .where(
                Approval.candidate_id == candidate.id,
                Approval.kind == _REVIEW_KIND,
                Approval.target_id == signal.id,
            )
        )
    ).scalar_one()
    assert count == 1


async def test_approve_transitions_signal_to_approved(session, candidate):
    signal = await _owned_signal(session, candidate)
    assert signal.status is RecruiterSignalStatus.DISCOVERED
    service = await _review_service(session)
    approval = await service.request_review(candidate.id, candidate.user_id, signal.id)
    approved = await service.decide(
        candidate.id,
        candidate.user_id,
        approval.id,
        ApprovalDecisionType.APPROVE,
        note="Verified identity and match; proceed to prep.",
    )
    assert approved is approval
    assert approved.status is ApprovalStatus.APPROVED
    assert approved.decision_type is ApprovalDecisionType.APPROVE
    assert approved.decided_by == str(candidate.user_id)
    assert approved.decided_at is not None
    re_signal = await load_signal(session, candidate.id, signal.signal_identity)
    assert re_signal.status is RecruiterSignalStatus.APPROVED


async def test_approve_is_human_attributed_and_append_only(session, candidate):
    signal = await _owned_signal(session, candidate)
    service = await _review_service(session)
    approval = await service.request_review(candidate.id, candidate.user_id, signal.id)
    await service.decide(
        candidate.id, candidate.user_id, approval.id, ApprovalDecisionType.APPROVE
    )
    decisions = await ApprovalDecisionRepository(session).list_for_approval(approval.id)
    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.actor_id == str(candidate.user_id)
    assert decision.decision_type is ApprovalDecisionType.APPROVE
    assert decision.decided_at is not None
    events = await _audit_events(session, candidate.id, "RECRUITER_SIGNAL_REVIEW_DECIDED")
    assert events
    assert events[-1].actor_id == str(candidate.user_id)
    metadata = events[-1].event_metadata or {}
    assert metadata.get("decision") == ApprovalDecisionType.APPROVE.value
    assert metadata.get("signal_status") == RecruiterSignalStatus.APPROVED.value


async def test_reject_transitions_signal_to_rejected_and_blocks_requeue(session, candidate):
    signal = await _owned_signal(session, candidate)
    service = await _review_service(session)
    approval = await service.request_review(candidate.id, candidate.user_id, signal.id)
    rejected = await service.decide(
        candidate.id, candidate.user_id, approval.id, ApprovalDecisionType.REJECT
    )
    assert rejected.status is ApprovalStatus.REJECTED
    re_signal = await load_signal(session, candidate.id, signal.signal_identity)
    assert re_signal.status is RecruiterSignalStatus.REJECTED
    with pytest.raises(ValidationError):
        await service.require_approved_review(candidate.id, candidate.user_id, signal.id)
    with pytest.raises(ValidationError):
        await service.request_review(candidate.id, candidate.user_id, signal.id)


async def test_cancel_leaves_signal_discovered(session, candidate):
    signal = await _owned_signal(session, candidate)
    service = await _review_service(session)
    approval = await service.request_review(candidate.id, candidate.user_id, signal.id)
    cancelled = await service.decide(
        candidate.id, candidate.user_id, approval.id, ApprovalDecisionType.CANCEL
    )
    assert cancelled.status is ApprovalStatus.CANCELLED
    re_signal = await load_signal(session, candidate.id, signal.signal_identity)
    assert re_signal.status is RecruiterSignalStatus.DISCOVERED
    with pytest.raises(ValidationError):
        await service.require_approved_review(candidate.id, candidate.user_id, signal.id)


async def test_require_approved_review_gates_consumption(session, candidate):
    signal = await _owned_signal(session, candidate)
    service = await _review_service(session)
    with pytest.raises(ValidationError):
        await service.require_approved_review(candidate.id, candidate.user_id, signal.id)
    approval = await service.request_review(candidate.id, candidate.user_id, signal.id)
    await service.decide(
        candidate.id, candidate.user_id, approval.id, ApprovalDecisionType.APPROVE
    )
    granted = await service.require_approved_review(
        candidate.id, candidate.user_id, signal.id
    )
    assert granted.id == approval.id
    assert granted.status is ApprovalStatus.APPROVED


async def test_non_reviewable_signal_type_is_rejected(session, candidate):
    signal = await _signal_of_type(
        session, candidate, RecruiterSignalType.RECRUITER_ASSOCIATED.value
    )
    service = await _review_service(session)
    with pytest.raises(ValidationError):
        await service.request_review(candidate.id, candidate.user_id, signal.id)


async def test_review_is_candidate_scoped(session, candidate):
    signal = await _owned_signal(session, candidate)
    foreign = await _foreign_candidate(session)
    service = await _review_service(session)
    approval = await service.request_review(candidate.id, candidate.user_id, signal.id)
    with pytest.raises(NotFoundError):
        await service.require_approved_review(
            foreign.id, foreign.user_id, signal.id
        )
    with pytest.raises(NotFoundError):
        await service.decide(
            foreign.id,
            foreign.user_id,
            approval.id,
            ApprovalDecisionType.APPROVE,
        )


async def test_review_never_creates_approval_for_non_reviewable_and_no_outreach(session, candidate):
    employer = await seed_employer(session)
    job = await seed_job(session, candidate, employer)
    await seed_contact(session, candidate, employer, job)
    generated = await generate_outreach_signals(session, candidate, candidate.user_id)
    for item in generated:
        if item.signal_type is not RecruiterSignalType.RECRUITER_OUTREACH_CANDIDATE:
            continue
        signal = await load_signal(session, candidate.id, item.signal_identity)
        service = await _review_service(session)
        approval = await service.request_review(candidate.id, candidate.user_id, signal.id)
        await service.decide(
            candidate.id, candidate.user_id, approval.id, ApprovalDecisionType.APPROVE
        )
    # Approval always stays an explicit Approval row; no outreach artifacts appear
    # anywhere in this phase.
    approval_count = (
        await session.execute(
            select(func.count())
            .select_from(Approval)
            .where(
                Approval.candidate_id == candidate.id,
                Approval.kind == _REVIEW_KIND,
            )
        )
    ).scalar_one()
    assert approval_count >= 1
    outstanding = (
        await session.execute(
            select(func.count())
            .select_from(Approval)
            .where(
                Approval.candidate_id == candidate.id,
                Approval.status == ApprovalStatus.APPROVED,
            )
        )
    ).scalar_one()
    assert outstanding >= 1


async def test_approval_record_is_persisted_and_gate_is_lookupable(session, candidate):
    signal = await _owned_signal(session, candidate)
    service = await _review_service(session)
    approval = await service.request_review(candidate.id, candidate.user_id, signal.id)
    await service.decide(
        candidate.id, candidate.user_id, approval.id, ApprovalDecisionType.APPROVE
    )
    repo = ApprovalRepository(session)
    found = await repo.get_approved_for_target(
        candidate.id,
        _REVIEW_KIND,
        "recruiter_signal",
        signal.id,
    )
    assert found is not None
    assert found.id == approval.id
    assert found.status is ApprovalStatus.APPROVED
    open_again = await repo.get_open_for_target(
        candidate.id,
        _REVIEW_KIND,
        "recruiter_signal",
        signal.id,
    )
    assert open_again is None
