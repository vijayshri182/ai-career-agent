"""CP16: Recruiter signal domain model tests.

Covers the data/model foundation only: deterministic identity and dedup,
controlled vocabulary, unknown fields stay NULL, explicit lifecycle
transitions, candidate ownership, and the hard security boundary (no
network/outreach/contact-generation imports reachable from the domain code).
"""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import NotFoundError, ValidationError
from backend.models.recruiter_signal import (
    RecruiterSignal,
    RecruiterSignalStatus,
    RecruiterSignalType,
)
from backend.schemas.recruiter_signal import RecruiterSignalCreate

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ------------------------------------------------------------------------ #
# Fixtures / helpers
# ------------------------------------------------------------------------ #


async def _company(session: AsyncSession):
    from backend.repositories.company import CompanyRepository

    company = await CompanyRepository(session).create(
        name="Signal Corp", website_domain="signalcorp.example"
    )
    await session.flush()
    return company


async def _job(session: AsyncSession, candidate_id, company):
    from backend.models.job import Job
    from backend.models.job_source import JobSource, JobSourceType

    source = JobSource(
        candidate_id=candidate_id,
        name=f"cp16-source-{uuid4().hex[:6]}",
        source_type=JobSourceType.JOB_BOARD,
        base_url="https://feed.example/jobs.xml",
    )
    session.add(source)
    await session.flush()
    job = Job(
        candidate_id=candidate_id,
        company_id=company.id,
        source_id=source.id,
        url=f"https://careers.signalcorp.example/jobs/{uuid4().hex[:8]}",
        title="Senior Engineer",
        content_hash=f"cp16-{uuid4().hex[:12]}",
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    session.add(job)
    await session.flush()
    return job


async def _contact(session: AsyncSession, candidate_id, company):
    from backend.models.recruiter_contact import (
        ContactSource,
        ContactSourceType,
        ContactType,
        RecruiterContact,
    )

    source = ContactSource(
        candidate_id=candidate_id,
        company_id=company.id,
        source_type=ContactSourceType.TEAM_PAGE,
        url="https://signalcorp.example/team",
    )
    session.add(source)
    await session.flush()
    contact = RecruiterContact(
        candidate_id=candidate_id,
        company_id=company.id,
        source_id=source.id,
        full_name="Avery Recruiter",
        role_title="Talent Partner",
        public_profile_url=f"https://linkedin.example/in/avery-{uuid4().hex[:6]}",
        confidence_score=88,
        contact_type=ContactType.VERIFIED,
    )
    session.add(contact)
    await session.flush()
    return contact


async def _foreign_candidate(session: AsyncSession):
    from backend.repositories.candidate import CandidateRepository
    from backend.repositories.user import UserRepository

    user = await UserRepository(session).create_user(
        f"cp16-foreign-{uuid4().hex[:8]}@example.com", "ForeignPass123!"
    )
    candidate = await CandidateRepository(session).create_for_user(
        user_id=user.id, full_name="Foreign Candidate", email="foreign@example.com"
    )
    await session.flush()
    return candidate


def _service(session: AsyncSession):
    from backend.repositories.audit import AuditRepository
    from backend.repositories.candidate import CandidateRepository
    from backend.repositories.company import CompanyRepository
    from backend.repositories.job import JobRepository
    from backend.repositories.recruiter_contact import RecruiterContactRepository
    from backend.repositories.recruiter_signal import RecruiterSignalRepository
    from backend.services.recruiter_signal import RecruiterSignalService

    return RecruiterSignalService(
        signal_repo=RecruiterSignalRepository(session),
        contact_repo=RecruiterContactRepository(session),
        job_repo=JobRepository(session),
        company_repo=CompanyRepository(session),
        candidate_repo=CandidateRepository(session),
        audit_repo=AuditRepository(session),
    )


async def _count_all(session: AsyncSession, candidate_id) -> int:
    result = await session.execute(
        select(RecruiterSignal)
        .where(RecruiterSignal.candidate_id == candidate_id)
        .order_by(RecruiterSignal.signal_identity)
    )
    return len(result.scalars().all())


# ------------------------------------------------------------------------ #
# Creation: defaults, unknown fields, controlled vocabulary
# ------------------------------------------------------------------------ #


async def test_create_signal_defaults_to_discovered(session, candidate):
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    service = _service(session)

    signal = await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job.id,
            signal_type=RecruiterSignalType.RECRUITER_ASSOCIATED,
            source="gate4e-evidence",
        ),
    )

    assert signal.candidate_id == candidate.id
    assert signal.job_id == job.id
    assert signal.signal_type is RecruiterSignalType.RECRUITER_ASSOCIATED
    assert signal.status is RecruiterSignalStatus.DISCOVERED
    assert len(signal.signal_identity) == 64
    assert signal.source == "gate4e-evidence"
    assert signal.source_reference is None
    assert signal.recruiter_contact_id is None
    assert signal.company_id is None
    assert signal.evidence_json == {}
    assert signal.provenance_json == {}


async def test_create_signal_never_implicitly_approved(session, candidate):
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    service = _service(session)

    signal = await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job.id,
            signal_type=RecruiterSignalType.RECRUITER_ROLE_RELEVANT,
            source="gate4e-evidence",
        ),
    )

    assert signal.status is RecruiterSignalStatus.DISCOVERED
    assert signal.status is not RecruiterSignalStatus.APPROVED
    assert signal.status is not RecruiterSignalStatus.READY_FOR_REVIEW


async def test_create_signal_with_contact_and_company(session, candidate):
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    contact = await _contact(session, candidate.id, company)
    service = _service(session)

    signal = await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job.id,
            recruiter_contact_id=contact.id,
            company_id=company.id,
            signal_type=RecruiterSignalType.RECRUITER_CONTACT_AVAILABLE,
            source="gate4e-evidence",
            evidence={"shows": "public team page lists a recruiting contact"},
            provenance={"producer": "gate4e", "version": "2"},
        ),
    )

    assert signal.recruiter_contact_id == contact.id
    assert signal.company_id == company.id
    assert signal.evidence_json["shows"]
    assert signal.provenance_json == {"producer": "gate4e", "version": "2"}


async def test_unknown_recruiter_is_null_not_fabricated(session, candidate):
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    service = _service(session)

    signal = await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job.id,
            signal_type=RecruiterSignalType.RECRUITER_ROLE_RELEVANT,
            source="gate4e-evidence",
            evidence={"role": "talent acquisition mentioned on careers page"},
        ),
    )

    assert signal.recruiter_contact_id is None
    assert signal.evidence_json["role"]


async def test_role_relevant_cannot_reference_a_contact(session, candidate):
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    contact = await _contact(session, candidate.id, company)
    service = _service(session)

    with pytest.raises(ValidationError):
        await service.create_signal(
            candidate.id,
            candidate.user_id,
            RecruiterSignalCreate(
                job_id=job.id,
                recruiter_contact_id=contact.id,
                signal_type=RecruiterSignalType.RECRUITER_ROLE_RELEVANT,
                source="gate4e-evidence",
            ),
        )


async def test_contact_available_requires_a_contact(session, candidate):
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    service = _service(session)

    with pytest.raises(ValidationError):
        await service.create_signal(
            candidate.id,
            candidate.user_id,
            RecruiterSignalCreate(
                job_id=job.id,
                signal_type=RecruiterSignalType.RECRUITER_CONTACT_AVAILABLE,
                source="gate4e-evidence",
            ),
        )


async def test_outreach_candidate_requires_a_contact(session, candidate):
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    service = _service(session)

    with pytest.raises(ValidationError):
        await service.create_signal(
            candidate.id,
            candidate.user_id,
            RecruiterSignalCreate(
                job_id=job.id,
                signal_type=RecruiterSignalType.RECRUITER_OUTREACH_CANDIDATE,
                source="gate4e-evidence",
            ),
        )


async def test_create_scoped_to_owned_job(session, candidate):
    foreign = await _foreign_candidate(session)
    company = await _company(session)
    foreign_job = await _job(session, foreign.id, company)
    service = _service(session)

    with pytest.raises(NotFoundError):
        await service.create_signal(
            candidate.id,
            candidate.user_id,
            RecruiterSignalCreate(
                job_id=foreign_job.id,
                signal_type=RecruiterSignalType.RECRUITER_ASSOCIATED,
                source="gate4e-evidence",
            ),
        )


async def test_create_scoped_to_owned_contact(session, candidate):
    foreign = await _foreign_candidate(session)
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    foreign_contact = await _contact(session, foreign.id, company)
    service = _service(session)

    with pytest.raises(NotFoundError):
        await service.create_signal(
            candidate.id,
            candidate.user_id,
            RecruiterSignalCreate(
                job_id=job.id,
                recruiter_contact_id=foreign_contact.id,
                signal_type=RecruiterSignalType.RECRUITER_CONTACT_AVAILABLE,
                source="gate4e-evidence",
            ),
        )


async def test_create_unknown_company_raises_not_found(session, candidate):
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    service = _service(session)

    with pytest.raises(NotFoundError):
        await service.create_signal(
            candidate.id,
            candidate.user_id,
            RecruiterSignalCreate(
                job_id=job.id,
                company_id=uuid4(),
                signal_type=RecruiterSignalType.RECRUITER_ASSOCIATED,
                source="gate4e-evidence",
            ),
        )


async def test_create_logs_audit_event(session, candidate):
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    service = _service(session)

    await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job.id,
            signal_type=RecruiterSignalType.RECRUITER_ASSOCIATED,
            source="gate4e-evidence",
        ),
    )
    await session.flush()

    from backend.repositories.audit import AuditRepository

    events = await AuditRepository(session).list_for_candidate(candidate.id)
    assert any(e.event_type == "RECRUITER_SIGNAL_CREATED" for e in events)


# ------------------------------------------------------------------------ #
# Deterministic identity and dedup
# ------------------------------------------------------------------------ #


async def test_replay_is_noop_single_record(session, candidate):
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    service = _service(session)

    create = RecruiterSignalCreate(
        job_id=job.id,
        signal_type=RecruiterSignalType.RECRUITER_ASSOCIATED,
        source="gate4e-evidence",
        source_reference="posting:r-100",
    )
    first = await service.create_signal(candidate.id, candidate.user_id, create)
    second = await service.create_signal(candidate.id, candidate.user_id, create)

    assert first.id == second.id
    assert await _count_all(session, candidate.id) == 1


async def test_identity_is_independent_of_evidence(session, candidate):
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    service = _service(session)

    first = await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job.id,
            signal_type=RecruiterSignalType.RECRUITER_ASSOCIATED,
            source="gate4e-evidence",
            evidence={"version": 1},
        ),
    )
    second = await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job.id,
            signal_type=RecruiterSignalType.RECRUITER_ASSOCIATED,
            source="gate4e-evidence",
            evidence={"version": 2},
        ),
    )

    assert first.id == second.id
    assert await _count_all(session, candidate.id) == 1
    persisted = await session.get(RecruiterSignal, first.id)
    assert persisted.evidence_json == {"version": 1}


async def test_identity_differentiates_identified_contact(session, candidate):
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    contact = await _contact(session, candidate.id, company)
    service = _service(session)

    a = await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job.id,
            signal_type=RecruiterSignalType.RECRUITER_ASSOCIATED,
            source="gate4e-evidence",
        ),
    )
    b = await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job.id,
            recruiter_contact_id=contact.id,
            signal_type=RecruiterSignalType.RECRUITER_ASSOCIATED,
            source="gate4e-evidence",
        ),
    )

    assert a.id != b.id
    assert a.signal_identity != b.signal_identity
    assert await _count_all(session, candidate.id) == 2


async def test_identity_differentiates_signal_type(session, candidate):
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    service = _service(session)

    a = await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job.id,
            signal_type=RecruiterSignalType.RECRUITER_ASSOCIATED,
            source="gate4e-evidence",
        ),
    )
    b = await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job.id,
            signal_type=RecruiterSignalType.RECRUITER_ROLE_RELEVANT,
            source="gate4e-evidence",
        ),
    )

    assert a.id != b.id
    assert a.signal_identity != b.signal_identity
    assert await _count_all(session, candidate.id) == 2


async def test_identity_differentiates_job(session, candidate):
    company = await _company(session)
    job_a = await _job(session, candidate.id, company)
    job_b = await _job(session, candidate.id, company)
    service = _service(session)

    a = await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job_a.id,
            signal_type=RecruiterSignalType.RECRUITER_ASSOCIATED,
            source="gate4e-evidence",
        ),
    )
    b = await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job_b.id,
            signal_type=RecruiterSignalType.RECRUITER_ASSOCIATED,
            source="gate4e-evidence",
        ),
    )

    assert a.id != b.id
    assert a.signal_identity != b.signal_identity


# ------------------------------------------------------------------------ #
# Lifecycle transitions
# ------------------------------------------------------------------------ #


async def test_discovered_to_ready_for_review(session, candidate):
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    service = _service(session)

    signal = await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job.id,
            signal_type=RecruiterSignalType.RECRUITER_ASSOCIATED,
            source="gate4e-evidence",
        ),
    )
    updated = await service.update_status(
        candidate.id,
        candidate.user_id,
        signal.id,
        RecruiterSignalStatus.READY_FOR_REVIEW,
    )

    assert updated.status is RecruiterSignalStatus.READY_FOR_REVIEW
    refreshed = await session.get(RecruiterSignal, signal.id)
    assert refreshed.status is RecruiterSignalStatus.READY_FOR_REVIEW


async def test_approved_requires_explicit_human_path(session, candidate):
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    service = _service(session)

    signal = await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job.id,
            signal_type=RecruiterSignalType.RECRUITER_ASSOCIATED,
            source="gate4e-evidence",
        ),
    )

    with pytest.raises(ValidationError):
        await service.update_status(
            candidate.id,
            candidate.user_id,
            signal.id,
            RecruiterSignalStatus.APPROVED,
        )

    await service.update_status(
        candidate.id,
        candidate.user_id,
        signal.id,
        RecruiterSignalStatus.READY_FOR_REVIEW,
    )
    approved = await service.update_status(
        candidate.id,
        candidate.user_id,
        signal.id,
        RecruiterSignalStatus.APPROVED,
    )
    assert approved.status is RecruiterSignalStatus.APPROVED


async def test_rejected_then_expired_transitions(session, candidate):
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    service = _service(session)

    signal = await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job.id,
            signal_type=RecruiterSignalType.RECRUITER_ASSOCIATED,
            source="gate4e-evidence",
        ),
    )
    await service.update_status(
        candidate.id,
        candidate.user_id,
        signal.id,
        RecruiterSignalStatus.READY_FOR_REVIEW,
    )
    rejected = await service.update_status(
        candidate.id,
        candidate.user_id,
        signal.id,
        RecruiterSignalStatus.REJECTED,
    )
    assert rejected.status is RecruiterSignalStatus.REJECTED

    with pytest.raises(ValidationError):
        await service.update_status(
            candidate.id,
            candidate.user_id,
            signal.id,
            RecruiterSignalStatus.READY_FOR_REVIEW,
        )

    expired = await service.update_status(
        candidate.id,
        candidate.user_id,
        signal.id,
        RecruiterSignalStatus.EXPIRED,
    )
    assert expired.status is RecruiterSignalStatus.EXPIRED


async def test_terminal_states_have_no_outgoing_transitions(session, candidate):
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    service = _service(session)

    signal = await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job.id,
            signal_type=RecruiterSignalType.RECRUITER_ASSOCIATED,
            source="gate4e-evidence",
        ),
    )
    expired = await service.update_status(
        candidate.id,
        candidate.user_id,
        signal.id,
        RecruiterSignalStatus.EXPIRED,
    )
    assert expired.status is RecruiterSignalStatus.EXPIRED

    for state in (
        RecruiterSignalStatus.DISCOVERED,
        RecruiterSignalStatus.EVIDENCE_PENDING,
        RecruiterSignalStatus.READY_FOR_REVIEW,
        RecruiterSignalStatus.APPROVED,
        RecruiterSignalStatus.REJECTED,
    ):
        with pytest.raises(ValidationError):
            await service.update_status(candidate.id, candidate.user_id, signal.id, state)


async def test_same_status_update_is_noop(session, candidate):
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    service = _service(session)

    signal = await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job.id,
            signal_type=RecruiterSignalType.RECRUITER_ASSOCIATED,
            source="gate4e-evidence",
        ),
    )
    updated = await service.update_status(
        candidate.id,
        candidate.user_id,
        signal.id,
        RecruiterSignalStatus.DISCOVERED,
    )
    assert updated.id == signal.id
    assert updated.status is RecruiterSignalStatus.DISCOVERED


async def test_evidence_pending_round_trip(session, candidate):
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    contact = await _contact(session, candidate.id, company)
    service = _service(session)

    signal = await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job.id,
            recruiter_contact_id=contact.id,
            signal_type=RecruiterSignalType.RECRUITER_CONTACT_AVAILABLE,
            source="gate4e-evidence",
        ),
    )
    pending = await service.update_status(
        candidate.id,
        candidate.user_id,
        signal.id,
        RecruiterSignalStatus.EVIDENCE_PENDING,
    )
    assert pending.status is RecruiterSignalStatus.EVIDENCE_PENDING
    ready = await service.update_status(
        candidate.id,
        candidate.user_id,
        signal.id,
        RecruiterSignalStatus.READY_FOR_REVIEW,
    )
    assert ready.status is RecruiterSignalStatus.READY_FOR_REVIEW


# ------------------------------------------------------------------------ #
# Read paths and ownership
# ------------------------------------------------------------------------ #


async def test_get_signal_owned(session, candidate):
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    service = _service(session)

    signal = await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job.id,
            signal_type=RecruiterSignalType.RECRUITER_ASSOCIATED,
            source="gate4e-evidence",
        ),
    )
    fetched = await service.get_signal(candidate.id, candidate.user_id, signal.id)
    assert fetched.id == signal.id


async def test_get_signal_missing_raises_not_found(session, candidate):
    service = _service(session)
    with pytest.raises(NotFoundError):
        await service.get_signal(candidate.id, candidate.user_id, uuid4())


async def test_list_filters_by_status_and_type(session, candidate):
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    service = _service(session)

    a = await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job.id,
            signal_type=RecruiterSignalType.RECRUITER_ASSOCIATED,
            source="gate4e-evidence",
        ),
    )
    b = await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job.id,
            signal_type=RecruiterSignalType.RECRUITER_ROLE_RELEVANT,
            source="gate4e-evidence",
        ),
    )
    await service.update_status(
        candidate.id, candidate.user_id, b.id, RecruiterSignalStatus.READY_FOR_REVIEW
    )

    all_signals = await service.list_signals(candidate.id, candidate.user_id)
    assert {s.id for s in all_signals} == {a.id, b.id}

    ready = await service.list_signals(
        candidate.id, candidate.user_id, status=RecruiterSignalStatus.READY_FOR_REVIEW
    )
    assert [s.id for s in ready] == [b.id]

    associated = await service.list_signals(
        candidate.id,
        candidate.user_id,
        signal_type=RecruiterSignalType.RECRUITER_ASSOCIATED,
    )
    assert [s.id for s in associated] == [a.id]


async def test_list_orders_most_recent_first(session, candidate):
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    service = _service(session)

    ids = []
    for i in range(3):
        signal = await service.create_signal(
            candidate.id,
            candidate.user_id,
            RecruiterSignalCreate(
                job_id=job.id,
                signal_type=RecruiterSignalType.RECRUITER_ASSOCIATED,
                source=f"gate4e-evidence-{i}",
            ),
        )
        ids.append(signal.id)

    ordered = await service.list_signals(candidate.id, candidate.user_id)
    assert [s.id for s in ordered] == list(reversed(ids))


async def test_count_signals(session, candidate):
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    service = _service(session)

    await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job.id,
            signal_type=RecruiterSignalType.RECRUITER_ASSOCIATED,
            source="gate4e-evidence",
        ),
    )
    await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job.id,
            signal_type=RecruiterSignalType.RECRUITER_ROLE_RELEVANT,
            source="gate4e-evidence",
        ),
    )

    assert await service.count_signals(candidate.id, candidate.user_id) == 2
    assert (
        await service.count_signals(
            candidate.id,
            candidate.user_id,
            signal_type=RecruiterSignalType.RECRUITER_ROLE_RELEVANT,
        )
        == 1
    )


async def test_foreign_candidate_rejected_across_operations(session, candidate):
    foreign = await _foreign_candidate(session)
    company = await _company(session)
    job = await _job(session, candidate.id, company)
    service = _service(session)

    await service.create_signal(
        candidate.id,
        candidate.user_id,
        RecruiterSignalCreate(
            job_id=job.id,
            signal_type=RecruiterSignalType.RECRUITER_ASSOCIATED,
            source="gate4e-evidence",
        ),
    )

    with pytest.raises(NotFoundError):
        await service.create_signal(
            foreign.id,
            candidate.user_id,
            RecruiterSignalCreate(
                job_id=job.id,
                signal_type=RecruiterSignalType.RECRUITER_ASSOCIATED,
                source="gate4e-evidence",
            ),
        )
    with pytest.raises(NotFoundError):
        await service.get_signal(foreign.id, candidate.user_id, uuid4())
    with pytest.raises(NotFoundError):
        await service.list_signals(foreign.id, candidate.user_id)
    with pytest.raises(NotFoundError):
        await service.count_signals(foreign.id, candidate.user_id)
    with pytest.raises(NotFoundError):
        await service.update_status(
            foreign.id, candidate.user_id, uuid4(), RecruiterSignalStatus.EXPIRED
        )

    assert await _count_all(session, candidate.id) == 1


# ------------------------------------------------------------------------ #
# Security boundary: no network / outreach / contact generation
# ------------------------------------------------------------------------ #


_FORBIDDEN_MODULES = {
    "backend.services.outreach",
    "backend.services.recruiter_discovery",
    "backend.services.service_smtp",
    "backend.models.outreach",
    "httpx",
    "requests",
    "urllib",
    "urllib.request",
    "urllib.parse",
    "socket",
    "ssl",
    "playwright",
    "selenium",
    "aiohttp",
    "asyncio",
}


@pytest.mark.parametrize(
    "relative",
    [
        "src/backend/models/recruiter_signal.py",
        "src/backend/repositories/recruiter_signal.py",
        "src/backend/services/recruiter_signal.py",
        "src/backend/schemas/recruiter_signal.py",
        "migrations/versions/d16a7c9e52b0_add_recruiter_signal_foundation.py",
    ],
)
def test_cp16_sources_do_not_import_network_or_outreach_modules(relative):
    import ast

    source = (_PROJECT_ROOT / relative).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    top_level = {name.split(".")[0] for name in imported}
    assert not (_FORBIDDEN_MODULES & set(imported)), f"{relative} imports forbidden: "
    assert not (_FORBIDDEN_MODULES & top_level), f"{relative} imports forbidden: "


def test_cp16_domain_code_is_offline_by_construction():
    import ast

    forbids = {"start_browser", "launch", "crawl", "fetch", "send_email", "send_outreach"}
    for relative in (
        "src/backend/models/recruiter_signal.py",
        "src/backend/repositories/recruiter_signal.py",
        "src/backend/services/recruiter_signal.py",
    ):
        source = (_PROJECT_ROOT / relative).read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        calls |= {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
        }
        assert not (forbids & calls), f"{relative} must not contain outbound calls"
        if "OutreachMessage(" in source:
            raise AssertionError(f"{relative} must not construct OutreachMessage")
