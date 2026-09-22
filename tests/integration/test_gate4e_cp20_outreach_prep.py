"""CP20 outreach preparation from approved signal integration tests.

Preparation turns an APPROVED (human-reviewed) outreach-candidate signal into a
deterministic, grounded outreach draft artifact. It is gated on the exact human
approval bound in CP19, carries the full signal/evidence linkage, and never
persists a message or run -- sending remains a separate, explicitly approved
step (CP21/22/23).
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import NotFoundError, ValidationError
from backend.models.approval import ApprovalDecisionType
from backend.models.audit import AuditEvent
from backend.models.outreach import OutreachChannel, OutreachMessage, OutreachRun
from backend.models.recruiter_contact import ContactType
from backend.models.recruiter_signal import RecruiterSignalStatus, RecruiterSignalType
from backend.repositories.recruiter_contact import RecruiterContactRepository
from backend.schemas.recruiter_signal_outreach_prep import (
    RECRUITER_SIGNAL_OUTREACH_PREP_VERSION,
)
from backend.services.outreach_writer import OUTREACH_RULES_VERSION
from tests.integration.gate4e_signal_support import (
    build_approval_service,
    build_prep_service,
    generate_outreach_signals,
    load_signal,
    outreach_candidate,
    seed_contact,
    seed_employer,
    seed_job,
)


async def _foreign_candidate(session: AsyncSession):
    from backend.repositories.candidate import CandidateRepository
    from backend.repositories.user import UserRepository

    user = await UserRepository(session).create_user(
        "cp20-foreign@example.com", "Cp20Password123!"
    )
    candidate = await CandidateRepository(session).create_for_user(
        user_id=user.id, full_name="Foreign CP20", email="foreign-cp20@example.com"
    )
    await session.flush()
    return candidate


async def _owned_signal(session: AsyncSession, candidate):
    employer = await seed_employer(session)
    job = await seed_job(session, candidate, employer)
    contact = await seed_contact(session, candidate, employer, job)
    generated = await generate_outreach_signals(session, candidate, candidate.user_id)
    identity = outreach_candidate(generated)
    assert identity is not None
    signal = await load_signal(session, candidate.id, identity)
    return employer, job, contact, signal


async def _approve(session: AsyncSession, candidate, signal):

    service = await build_approval_service(session)
    approval = await service.request_review(candidate.id, candidate.user_id, signal.id)
    decided = await service.decide(
        candidate.id,
        candidate.user_id,
        approval.id,
        ApprovalDecisionType.APPROVE,
        note="CP20 test: approved for preparation.",
    )
    return decided


async def _audit_events(session: AsyncSession, candidate_id, event_type: str):
    return (
        await session.execute(
            select(AuditEvent).where(
                AuditEvent.event_type == event_type,
                AuditEvent.candidate_id == str(candidate_id),
            )
        )
    ).scalars().all()


async def _count_messages(session: AsyncSession, candidate_id) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(OutreachMessage)
            .where(OutreachMessage.candidate_id == candidate_id)
        )
    ).scalar_one()


async def _count_runs(session: AsyncSession, candidate_id) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(OutreachRun)
            .where(OutreachRun.candidate_id == candidate_id)
        )
    ).scalar_one()


async def test_prepare_requires_approved_signal(session, candidate):
    _, _, _, signal = await _owned_signal(session, candidate)
    assert signal.status is RecruiterSignalStatus.DISCOVERED
    service = await build_prep_service(session)
    with pytest.raises(ValidationError):
        await service.prepare(candidate.id, candidate.user_id, signal.id)


async def test_prepare_rejects_non_outreach_signal(session, candidate):
    employer = await seed_employer(session)
    job = await seed_job(session, candidate, employer)
    await seed_contact(session, candidate, employer, job)
    generated = await generate_outreach_signals(session, candidate, candidate.user_id)
    other = next(
        (g for g in generated if g.signal_type.value != RecruiterSignalType.RECRUITER_OUTREACH_CANDIDATE.value),
        None,
    )
    assert other is not None, "expected at least one non-outreach signal"
    signal = await load_signal(session, candidate.id, other.signal_identity)
    service = await build_prep_service(session)
    with pytest.raises(ValidationError):
        await service.prepare(candidate.id, candidate.user_id, signal.id)


async def test_approved_signal_prepares_grounded_artifact_with_linkage(session, candidate):
    employer, job, contact, signal = await _owned_signal(session, candidate)
    approval = await _approve(session, candidate, signal)

    prep = await (await build_prep_service(session)).prepare(
        candidate.id, candidate.user_id, signal.id
    )

    assert prep.candidate_id == candidate.id
    assert prep.signal_id == signal.id
    assert prep.contact_id == contact.id
    assert prep.job_id == job.id
    assert prep.company_id == employer.id
    assert prep.channel is OutreachChannel.EMAIL
    assert prep.prep_version == RECRUITER_SIGNAL_OUTREACH_PREP_VERSION
    assert prep.rules_version == OUTREACH_RULES_VERSION
    assert prep.subject == f"Application for {job.title} at {employer.name}"
    assert job.title in prep.body
    assert employer.name in prep.body
    assert contact.full_name in prep.body
    assert prep.prep_id

    provenance = signal.provenance_json or {}
    assert prep.linkage.signal_id == signal.id
    assert prep.linkage.signal_identity == signal.signal_identity
    assert prep.linkage.evidence_reference == provenance.get("evidence_reference")
    assert prep.linkage.generation_version == provenance.get("generation_version")
    assert prep.linkage.signal_status == RecruiterSignalStatus.APPROVED.value
    assert prep.linkage.approval_id == approval.id

    signal_link_sources = [
        s for s in prep.fact_sources if s.get("kind") == "recruiter_signal"
    ]
    assert signal_link_sources, "prep must carry the signal linkage fact source"
    assert signal_link_sources[0]["text"] == signal.signal_identity

    events = await _audit_events(session, candidate.id, "RECRUITER_SIGNAL_OUTREACH_PREPARED")
    assert events
    metadata = events[-1].event_metadata or {}
    assert metadata.get("prep_id") == prep.prep_id
    assert metadata.get("prep_version") == RECRUITER_SIGNAL_OUTREACH_PREP_VERSION
    assert events[-1].actor_id == str(candidate.user_id)


async def test_prepare_is_deterministic(session, candidate):
    _, _, _, signal = await _owned_signal(session, candidate)
    await _approve(session, candidate, signal)
    service = await build_prep_service(session)
    first = await service.prepare(candidate.id, candidate.user_id, signal.id)
    second = await service.prepare(candidate.id, candidate.user_id, signal.id)
    assert first.prep_id == second.prep_id
    assert first.model_dump_deterministic() == second.model_dump_deterministic()


async def test_prepare_blocks_suppressed_contact(session, candidate):
    _, _, contact, signal = await _owned_signal(session, candidate)
    await _approve(session, candidate, signal)
    contact = await RecruiterContactRepository(session).update(
        contact, is_suppressed=True
    )
    await session.flush()
    prep_service = await build_prep_service(session)
    with pytest.raises(ValidationError):
        await prep_service.prepare(candidate.id, candidate.user_id, signal.id)


async def test_prepare_blocks_unverified_contact(session, candidate):
    _, _, contact, signal = await _owned_signal(session, candidate)
    await _approve(session, candidate, signal)
    contact = await RecruiterContactRepository(session).update(
        contact, contact_type=ContactType.GUESSED
    )
    await session.flush()
    prep_service = await build_prep_service(session)
    with pytest.raises(ValidationError):
        await prep_service.prepare(candidate.id, candidate.user_id, signal.id)


async def test_prepare_blocks_missing_email_destination(session, candidate):
    _, _, contact, signal = await _owned_signal(session, candidate)
    await _approve(session, candidate, signal)
    contact = await RecruiterContactRepository(session).update(contact, email=None)
    await session.flush()
    prep_service = await build_prep_service(session)
    with pytest.raises(ValidationError):
        await prep_service.prepare(candidate.id, candidate.user_id, signal.id)


async def test_prepare_persists_no_outreach_artifacts(session, candidate):
    _, _, _, signal = await _owned_signal(session, candidate)
    await _approve(session, candidate, signal)
    prep = await (await build_prep_service(session)).prepare(
        candidate.id, candidate.user_id, signal.id
    )
    assert prep.subject
    assert prep.body
    assert await _count_messages(session, candidate.id) == 0
    assert await _count_runs(session, candidate.id) == 0


async def test_prepare_is_candidate_scoped(session, candidate):
    _, _, _, signal = await _owned_signal(session, candidate)
    await _approve(session, candidate, signal)
    foreign = await _foreign_candidate(session)
    prep_service = await build_prep_service(session)
    with pytest.raises(NotFoundError):
        await prep_service.prepare(foreign.id, foreign.user_id, signal.id)


async def test_prepare_audit_is_candidate_scoped(session, candidate):
    _, _, _, signal = await _owned_signal(session, candidate)
    await _approve(session, candidate, signal)
    await (await build_prep_service(session)).prepare(
        candidate.id, candidate.user_id, signal.id
    )
    events = await _audit_events(session, candidate.id, "RECRUITER_SIGNAL_OUTREACH_PREPARED")
    assert len(events) == 1
    assert str(events[0].candidate_id) == str(candidate.id)
