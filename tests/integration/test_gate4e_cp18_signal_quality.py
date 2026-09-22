"""CP18 recruiter-signal quality and audit integration tests.

Real integration (no mocks): quality is evaluated over real persisted signals
produced by the CP17 generator and the CP16 recorder, and every evaluation
mirrors an append-only audit event. Quality evaluation is deterministic
(byte-identical output for identical persisted inputs) and read-only (it never
mutates the signal, never ranks, and never contacts anyone).
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import NotFoundError
from backend.models.audit import AuditEvent
from backend.models.job_match import JobMatch
from backend.schemas.recruiter_signal_quality import (
    RECRUITER_SIGNAL_QUALITY_VERSION,
    RecruiterSignalQualityReport,
    SignalQualitySeverity,
)
from tests.integration.gate4e_signal_support import (
    build_quality_service,
    generate_outreach_signals,
    outreach_candidate,
    seed_contact,
    seed_employer,
    seed_job,
)


async def _foreign_candidate(session: AsyncSession):
    from backend.repositories.candidate import CandidateRepository
    from backend.repositories.user import UserRepository

    user = await UserRepository(session).create_user(
        "cp18-foreign@example.com", "Cp18Password123!"
    )
    candidate = await CandidateRepository(session).create_for_user(
        user_id=user.id, full_name="Foreign CP18", email="foreign-cp18@example.com"
    )
    await session.flush()
    return candidate


async def _generate_signal(session: AsyncSession, candidate, user_id, job, employer):
    await seed_contact(session, candidate, employer, job)
    generated = await generate_outreach_signals(session, candidate, user_id)
    identity = outreach_candidate(generated)
    assert identity is not None, "expected an outreach-candidate signal"
    return await load_by_identity(session, candidate.id, identity)


async def load_by_identity(session: AsyncSession, candidate_id, identity):
    from backend.repositories.recruiter_signal import RecruiterSignalRepository

    signal = await RecruiterSignalRepository(session).find_by_identity(candidate_id, identity)
    assert signal is not None
    return signal


async def _evaluate(session: AsyncSession, candidate, user_id, signal_id):
    return await (await build_quality_service(session)).evaluate_signal(
        candidate.id, user_id, signal_id
    )


async def test_quality_report_shape_and_version(session, candidate):
    employer = await seed_employer(session)
    job = await seed_job(session, candidate, employer)
    signal = await _generate_signal(session, candidate, candidate.user_id, job=job, employer=employer)
    report = await _evaluate(session, candidate, candidate.user_id, signal.id)
    assert isinstance(report, RecruiterSignalQualityReport)
    assert report.quality_version == RECRUITER_SIGNAL_QUALITY_VERSION
    assert report.signal_id == signal.id
    assert report.passed is True
    assert report.evaluation_id
    assert len(report.checks) >= 6
    assert {c.check for c in report.checks} >= {
        "identity_present",
        "source_present",
        "provenance_present",
        "evidence_present",
        "type_coherence",
        "contact_resolvable",
        "supported_fields_coherent",
        "contact_methods_coherent",
        "lifecycle_safe",
    }
    assert report.failed_checks == []


async def test_quality_evaluation_is_deterministic(session, candidate):
    employer = await seed_employer(session)
    job = await seed_job(session, candidate, employer)
    signal = await _generate_signal(session, candidate, candidate.user_id, job=job, employer=employer)
    first = await _evaluate(session, candidate, candidate.user_id, signal.id)
    second = await _evaluate(session, candidate, candidate.user_id, signal.id)
    assert first.evaluation_id == second.evaluation_id
    assert first.model_dump_deterministic() == second.model_dump_deterministic()


async def test_quality_evaluation_is_read_only(session, candidate):
    employer = await seed_employer(session)
    job = await seed_job(session, candidate, employer)
    signal = await _generate_signal(session, candidate, candidate.user_id, job=job, employer=employer)
    identity_before = signal.signal_identity
    status_before = signal.status
    await _evaluate(session, candidate, candidate.user_id, signal.id)
    await session.flush()
    again = await (await build_quality_service(session)).evaluate_signal(
        candidate.id, candidate.user_id, signal.id
    )
    assert signal.signal_identity == identity_before
    assert signal.status is status_before
    assert again.passed


async def test_quality_audits_every_evaluation(session, candidate):
    employer = await seed_employer(session)
    job = await seed_job(session, candidate, employer)
    signal = await _generate_signal(session, candidate, candidate.user_id, job=job, employer=employer)
    await _evaluate(session, candidate, candidate.user_id, signal.id)
    events = (
        await session.execute(
            select(AuditEvent).where(
                AuditEvent.event_type == "RECRUITER_SIGNAL_QUALITY_EVALUATED",
                AuditEvent.candidate_id == str(candidate.id),
            )
        )
    ).scalars().all()
    assert events
    metadata = events[-1].event_metadata or {}
    assert metadata.get("passed") is True
    assert metadata.get("quality_version") == RECRUITER_SIGNAL_QUALITY_VERSION


async def test_quality_flags_incoherent_supported_fields(session, candidate):
    employer = await seed_employer(session)
    job = await seed_job(session, candidate, employer)
    signal = await _generate_signal(session, candidate, candidate.user_id, job=job, employer=employer)
    # Tamper: assert a recruiter field that is not declared in supported_fields.
    evidence = dict(signal.evidence_json or {})
    recruiter = dict(evidence.get("recruiter") or {})
    recruiter["email"] = "injected.claim@example.com"
    evidence["recruiter"] = recruiter
    evidence["supported_fields"] = [f for f in evidence.get("supported_fields", []) if f != "email"]
    signal.evidence_json = evidence
    await session.flush()
    report = await _evaluate(session, candidate, candidate.user_id, signal.id)
    assert report.passed is False
    assert "supported_fields_coherent" in report.failed_checks
    flagged = next(c for c in report.checks if c.check == "supported_fields_coherent")
    assert flagged.severity is SignalQualitySeverity.FAIL


async def test_quality_flags_missing_identity(session, candidate):
    employer = await seed_employer(session)
    job = await seed_job(session, candidate, employer)
    signal = await _generate_signal(session, candidate, candidate.user_id, job=job, employer=employer)
    signal.signal_identity = ""
    await session.flush()
    report = await _evaluate(session, candidate, candidate.user_id, signal.id)
    assert report.passed is False
    assert "identity_present" in report.failed_checks


async def test_quality_requires_owned_candidate(session, candidate):
    employer = await seed_employer(session)
    job = await seed_job(session, candidate, employer)
    signal = await _generate_signal(session, candidate, candidate.user_id, job=job, employer=employer)
    foreign = await _foreign_candidate(session)
    service = await build_quality_service(session)
    with pytest.raises(NotFoundError):
        await service.evaluate_signal(foreign.id, candidate.user_id, signal.id)


async def test_quality_contributes_no_jobmatches(session, candidate):
    employer = await seed_employer(session)
    job = await seed_job(session, candidate, employer)
    signal = await _generate_signal(session, candidate, candidate.user_id, job=job, employer=employer)
    await _evaluate(session, candidate, candidate.user_id, signal.id)
    count = (
        await session.execute(
            select(func.count())
            .select_from(JobMatch)
            .where(JobMatch.candidate_id == candidate.id)
        )
    ).scalar_one()
    assert count == 0


async def test_quality_evaluation_id_is_sha256(session, candidate):
    employer = await seed_employer(session)
    job = await seed_job(session, candidate, employer)
    signal = await _generate_signal(session, candidate, candidate.user_id, job=job, employer=employer)
    report = await _evaluate(session, candidate, candidate.user_id, signal.id)
    assert len(report.evaluation_id) == 64
    assert all(c in "0123456789abcdef" for c in report.evaluation_id)
