"""CP23 Gate 4E recruiter-signal end-to-end flow test.

Walks one recruiter outreach candidate signal through every stage of the
humans-in-the-loop pipeline and verifies the recorded outcome and audit chain:

    generate -> quality (CP18) -> human review approve (CP19) -> prepare (CP20)
    -> draft via the outreach engine -> human approve send (CP21) -> send via
    the recording sender (CP22) -> record response (CP22).

The send uses the same recording sender the existing outreach suite uses, so no
real outbound activity happens. Every stage is real persistence, no mocks.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import get_settings
from backend.core.exceptions import NotFoundError, ValidationError
from backend.models.approval import ApprovalDecisionType, ApprovalStatus
from backend.models.audit import AuditEvent
from backend.models.outreach import OutreachRunStatus, OutreachStatus, ResponseStatus
from backend.models.recruiter_signal import RecruiterSignalStatus
from backend.repositories.application import ApplicationRepository
from backend.repositories.approval import ApprovalDecisionRepository, ApprovalRepository
from backend.repositories.audit import AuditRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.certification import CertificationRepository
from backend.repositories.company import CompanyRepository
from backend.repositories.education import EducationRepository
from backend.repositories.experience import ExperienceRepository
from backend.repositories.job import JobRepository
from backend.repositories.job_match import JobMatchRepository
from backend.repositories.outreach import (
    OutreachMessageRepository,
    OutreachMessageVersionRepository,
    OutreachRunRepository,
)
from backend.repositories.recruiter_contact import RecruiterContactRepository
from backend.repositories.skill import SkillRepository
from backend.services.approval import ApprovalService
from backend.services.outreach import OutreachService
from backend.services.outreach_writer import OUTREACH_RULES_VERSION
from tests.integration.gate4e_signal_support import (
    build_approval_service,
    build_prep_service,
    build_quality_service,
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
        "cp23-foreign@example.com", "Cp23Password123!"
    )
    candidate = await CandidateRepository(session).create_for_user(
        user_id=user.id, full_name="Foreign CP23", email="foreign-cp23@example.com"
    )
    await session.flush()
    return candidate


async def _seed_flow(session: AsyncSession, candidate):
    employer = await seed_employer(session)
    job = await seed_job(session, candidate, employer)
    contact = await seed_contact(session, candidate, employer, job)
    generated = await generate_outreach_signals(session, candidate, candidate.user_id)
    identity = outreach_candidate(generated)
    assert identity is not None
    signal = await load_signal(session, candidate.id, identity)
    return employer, job, contact, signal


async def _build_outreach_services(session: AsyncSession, candidate, user_id):
    settings = get_settings()
    audit_repo = AuditRepository(session)
    approval_repo = ApprovalRepository(session)
    decision_repo = ApprovalDecisionRepository(session)
    approval_service = ApprovalService(
        approval_repo=approval_repo,
        decision_repo=decision_repo,
        candidate_repo=CandidateRepository(session),
        audit_repo=audit_repo,
        actor_id=user_id,
        candidate_id=candidate.id,
        autonomy_level=settings.autonomy_level,
    )
    outreach = OutreachService(
        candidate_repo=CandidateRepository(session),
        contact_repo=RecruiterContactRepository(session),
        job_repo=JobRepository(session),
        company_repo=CompanyRepository(session),
        skill_repo=SkillRepository(session),
        experience_repo=ExperienceRepository(session),
        education_repo=EducationRepository(session),
        certification_repo=CertificationRepository(session),
        match_repo=JobMatchRepository(session),
        application_repo=ApplicationRepository(session),
        message_repo=OutreachMessageRepository(session),
        version_repo=OutreachMessageVersionRepository(session),
        run_repo=OutreachRunRepository(session),
        audit_repo=audit_repo,
        approval_repo=approval_repo,
        approval_service=approval_service,
        actor_id=user_id,
        candidate_id=candidate.id,
        autonomy_level=settings.autonomy_level,
        approval_required=True,
        daily_limit=settings.outreach_daily_limit,
        max_attempts=settings.outreach_max_attempts,
        retry_base_seconds=settings.outreach_retry_base_seconds,
    )
    return approval_service, outreach


async def _audit_events(session: AsyncSession, candidate_id: UUID) -> list[AuditEvent]:
    return list(
        (
            await session.execute(
                select(AuditEvent)
                .where(AuditEvent.candidate_id == str(candidate_id))
                .order_by(
                    AuditEvent.created_at,
                    AuditEvent.entity_type,
                    AuditEvent.entity_id,
                )
            )
        ).scalars().all()
    )


async def test_end_to_end_signal_to_sent_outreach(session, candidate):
    employer, job, contact, signal = await _seed_flow(session, candidate)
    assert signal.status is RecruiterSignalStatus.DISCOVERED

    # CP18 quality gate
    quality = await build_quality_service(session)
    report = await quality.evaluate_signal(candidate.id, candidate.user_id, signal.id)
    assert report.passed, f"quality gate failed: {report.failed_checks}"

    # CP19 human review approve
    reviews = await build_approval_service(session)
    review = await reviews.request_review(candidate.id, candidate.user_id, signal.id)
    await reviews.decide(
        candidate.id,
        candidate.user_id,
        review.id,
        ApprovalDecisionType.APPROVE,
        note="E2E: identity and match verified.",
    )
    approved = await load_signal(session, candidate.id, signal.signal_identity)
    assert approved.status is RecruiterSignalStatus.APPROVED

    # CP20 grounded preparation pinned to the approval
    prep = await (await build_prep_service(session)).prepare(
        candidate.id, candidate.user_id, signal.id
    )
    assert prep.subject
    assert prep.body
    assert prep.linkage.approval_id == review.id

    # CP21/22 outreach engine: draft from the prep artifact, approve, send, respond
    send_approval_service, outreach = await _build_outreach_services(
        session, candidate, candidate.user_id
    )
    message = await outreach.create_draft(
        contact_id=contact.id,
        job_id=job.id,
        subject=prep.subject,
        body=prep.body,
    )
    assert message.status is OutreachStatus.DRAFT
    assert message.subject == prep.subject
    assert message.body == prep.body
    assert message.rules_version == OUTREACH_RULES_VERSION
    assert message.fact_sources, "grounded fact sources required on the message"

    send_approval = await outreach.submit_for_approval(message.id)
    assert send_approval is not None
    submitted = await outreach.get_message(message.id)
    assert submitted.status is OutreachStatus.PENDING_APPROVAL

    decided = await send_approval_service.decide(
        send_approval.id,
        ApprovalDecisionType.APPROVE,
        note="E2E: human approved this send.",
    )
    assert decided.status is ApprovalStatus.APPROVED

    run = await outreach.send(message.id)
    assert run.status is OutreachRunStatus.SENT
    assert run.provider_message_id == "RECORDED"
    assert run.candidate_id == candidate.id

    sent = await outreach.get_message(message.id)
    assert sent.status is OutreachStatus.SENT
    assert sent.response_status is ResponseStatus.NO_RESPONSE

    responded = await outreach.record_response(message.id, note="Scheduled a call")
    assert responded.response_status is ResponseStatus.RESPONDED

    # Audit chain: every stage logged, in pipeline order, for this candidate.
    events = await _audit_events(session, candidate.id)
    names = [e.event_type for e in events]
    expected = [
        "RECRUITER_SIGNAL_QUALITY_EVALUATED",
        "RECRUITER_SIGNAL_REVIEW_REQUESTED",
        "RECRUITER_SIGNAL_REVIEW_DECIDED",
        "RECRUITER_SIGNAL_OUTREACH_PREPARED",
        "outreach.drafted",
        "outreach.submitted_for_approval",
        "outreach.sent",
        "outreach.response_recorded",
    ]
    indices = [names.index(event_type) for event_type in expected]
    assert indices == sorted(indices), (
        "audit events must appear in pipeline order; saw " + ", ".join(names)
    )
    for event_type in expected:
        assert event_type in names


async def test_flow_prep_is_blocked_without_human_review(session, candidate):
    _, _, _, signal = await _seed_flow(session, candidate)
    prep_service = await build_prep_service(session)
    with pytest.raises(ValidationError):
        await prep_service.prepare(candidate.id, candidate.user_id, signal.id)


async def test_flow_send_is_blocked_without_human_draft_approval(session, candidate):
    _, _, contact, signal = await _seed_flow(session, candidate)
    review = await build_approval_service(session)
    approval = await review.request_review(candidate.id, candidate.user_id, signal.id)
    await review.decide(
        candidate.id,
        candidate.user_id,
        approval.id,
        ApprovalDecisionType.APPROVE,
        note="E2E: approved for prep only.",
    )
    prep = await (await build_prep_service(session)).prepare(
        candidate.id, candidate.user_id, signal.id
    )
    _, outreach = await _build_outreach_services(session, candidate, candidate.user_id)
    message = await outreach.create_draft(
        contact_id=contact.id,
        job_id=signal.job_id,
        subject=prep.subject,
        body=prep.body,
    )
    with pytest.raises(ValidationError):
        await outreach.send(message.id)


async def test_flow_is_candidate_scoped(session, candidate):
    _, _, _, signal = await _seed_flow(session, candidate)
    foreign = await _foreign_candidate(session)
    review = await build_approval_service(session)
    approval = await review.request_review(candidate.id, candidate.user_id, signal.id)
    await review.decide(
        candidate.id,
        candidate.user_id,
        approval.id,
        ApprovalDecisionType.APPROVE,
    )
    with pytest.raises(NotFoundError):
        await review.require_approved_review(foreign.id, foreign.user_id, signal.id)
    with pytest.raises(NotFoundError):
        await (await build_prep_service(session)).prepare(
            foreign.id, foreign.user_id, signal.id
        )
