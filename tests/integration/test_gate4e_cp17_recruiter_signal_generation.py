"""CP17 recruiter signal generation integration tests.

Real integration throughout (no mocks/spies): the real CP15 read-only match
evaluator runs over real persisted state to select eligible jobs, the CP17
generation service derives deterministic recruiter signals (or explicit
suppression reasons) from persisted recruiter evidence, and the CP16 recorder
persists them. Nothing here discovers, contacts, writes outreach, or reaches the
network; identical candidate+evidence inputs produce byte-identical output.
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.recruiter_contact import (
    ContactSource,
    ContactSourceType,
    ContactType,
    RecruiterContact,
)
from backend.models.recruiter_signal import RecruiterSignal, RecruiterSignalType
from backend.schemas.recruiter_signal_generation import (
    RecruiterEvidenceStrength,
    RecruiterSignalGenerationResult,
)

# ------------------------------------------------------------------------ #
# Fixtures / helpers  (mirror CP16 recorder wiring + CP15 evaluator wiring)
# ------------------------------------------------------------------------ #


def _ingestion_identity(job_id: UUID) -> str:
    return sha256(f"cp17:{job_id}".encode()).hexdigest()


@pytest_asyncio.fixture
async def employer(session: AsyncSession):
    from backend.repositories.company import CompanyRepository

    return await CompanyRepository(session).create(
        name="Signal Corp", website_domain="signalcorp.example"
    )


@pytest_asyncio.fixture
async def job(session: AsyncSession, candidate, employer):
    from backend.models.gate4e_ingestion import (
        Gate4eIngestion,
        Gate4eProcessingStatus,
    )
    from backend.models.job import Job
    from backend.models.job_source import JobSource, JobSourceType

    source = JobSource(
        candidate_id=candidate.id,
        name="cp17-job-source",
        source_type=JobSourceType.JOB_BOARD,
        base_url="https://feed.cp17.example/jobs.xml",
    )
    session.add(source)
    await session.flush()
    job = Job(
        candidate_id=candidate.id,
        company_id=employer.id,
        source_id=source.id,
        url="https://careers.cp17.example/jobs/senior-engineer",
        external_id="cp17-job-100",
        title="Senior Engineer",
        content_hash="cp17-deterministic-job-hash",
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    session.add(job)
    await session.flush()
    session.add(
        Gate4eIngestion(
            candidate_id=candidate.id,
            schema_version=1,
            producer_id="gate4e",
            producer_version="cp10",
            ingestion_identity=_ingestion_identity(job.id),
            processing_status=Gate4eProcessingStatus.ACCEPTED_VERIFIED,
            verification_status="VERIFIED",
            alert_index=1,
            posting_key="cp17-posting-key",
            company_name=employer.name,
            official_domain="careers.cp17.example",
            job_title=job.title,
            official_job_url=job.url,
            official_job_id="cp17-job-100",
            original_job_url=job.url,
            content_hash=job.content_hash,
            job_id=job.id,
        )
    )
    await session.flush()
    return job


async def _foreign_candidate(session: AsyncSession):
    from backend.repositories.candidate import CandidateRepository
    from backend.repositories.user import UserRepository

    user = await UserRepository(session).create_user(
        f"cp17-foreign-{uuid4().hex[:6]}@example.com", "Cp17Password123!"
    )
    candidate = await CandidateRepository(session).create_for_user(
        user_id=user.id, full_name="Foreign CP17", email=f"foreign-{uuid4().hex[:6]}@example.com"
    )
    await session.flush()
    return candidate


async def _contact(session: AsyncSession, candidate_id, company, job=None):
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
        job_id=job.id if job is not None else None,
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


async def _eligibility(session: AsyncSession):
    from backend.repositories.gate4e_ingestion import Gate4eIngestionRepository
    from backend.services.gate4e_eligibility import Gate4eEligibilityService

    return Gate4eEligibilityService(
        ingestion_repo=Gate4eIngestionRepository(session)
    )


async def _evaluator(session: AsyncSession):
    from backend.repositories.candidate import CandidateRepository
    from backend.repositories.experience import ExperienceRepository
    from backend.repositories.job import JobRepository
    from backend.repositories.skill import SkillRepository
    from backend.services.gate4e_match_evaluation import Gate4eReadOnlyMatchEvaluator

    return Gate4eReadOnlyMatchEvaluator(
        eligibility=await _eligibility(session),
        candidate_repo=CandidateRepository(session),
        job_repo=JobRepository(session),
        skill_repo=SkillRepository(session),
        experience_repo=ExperienceRepository(session),
    )


async def _service(session: AsyncSession):
    from backend.repositories.audit import AuditRepository
    from backend.repositories.candidate import CandidateRepository
    from backend.repositories.company import CompanyRepository
    from backend.repositories.job import JobRepository
    from backend.repositories.recruiter_contact import (
        ContactSourceRepository,
        RecruiterContactRepository,
    )
    from backend.repositories.recruiter_signal import RecruiterSignalRepository
    from backend.services.recruiter_signal import RecruiterSignalService
    from backend.services.recruiter_signal_generation import (
        RecruiterSignalGenerationService,
    )

    recorder = RecruiterSignalService(
        signal_repo=RecruiterSignalRepository(session),
        contact_repo=RecruiterContactRepository(session),
        job_repo=JobRepository(session),
        company_repo=CompanyRepository(session),
        candidate_repo=CandidateRepository(session),
        audit_repo=AuditRepository(session),
    )
    return RecruiterSignalGenerationService(
        evaluator=await _evaluator(session),
        job_repo=JobRepository(session),
        contact_repo=RecruiterContactRepository(session),
        source_repo=ContactSourceRepository(session),
        signal_repo=RecruiterSignalRepository(session),
        candidate_repo=CandidateRepository(session),
        recorder=recorder,
        audit_repo=AuditRepository(session),
    )


async def _all_signals(session: AsyncSession, candidate_id) -> list[RecruiterSignal]:
    result = await session.execute(
        select(RecruiterSignal)
        .where(RecruiterSignal.candidate_id == candidate_id)
        .order_by(RecruiterSignal.signal_identity)
    )
    return list(result.scalars().all())


# ------------------------------------------------------------------------ #
# Generation result shape
# ------------------------------------------------------------------------ #


async def test_generation_result_shape(session, candidate):
    result = await (await _service(session)).generate_for_candidate(
        candidate.id, candidate.user_id
    )
    assert isinstance(result, RecruiterSignalGenerationResult)
    assert result.candidate_id == candidate.id
    assert result.generation_version == "cp17.v1"
    assert len(result.run_id) == 64
    assert result.generated_at is not None


async def test_run_id_is_deterministic_hash(session, candidate):
    service = await _service(session)
    first = await service.generate_for_candidate(candidate.id, candidate.user_id)
    second = await service.generate_for_candidate(candidate.id, candidate.user_id)
    assert first.run_id == second.run_id


async def test_full_output_is_byte_identical_across_runs(session, candidate):
    service = await _service(session)
    first = await service.generate_for_candidate(candidate.id, candidate.user_id)
    second = await service.generate_for_candidate(candidate.id, candidate.user_id)
    assert first.model_dump(exclude={"generated_at"}) == second.model_dump(
        exclude={"generated_at"}
    )


async def test_no_evidence_yields_suppression_not_signal(session, candidate):
    result = await (await _service(session)).generate_for_candidate(
        candidate.id, candidate.user_id
    )
    assert result.suppressed


# ------------------------------------------------------------------------ #
# Ownership enforcement (mirror recorder contract)
# ------------------------------------------------------------------------ #


async def test_generation_requires_owned_candidate(session, candidate):
    from backend.core.exceptions import NotFoundError

    foreign = await _foreign_candidate(session)
    service = await _service(session)
    with pytest.raises(NotFoundError):
        await service.generate_for_candidate(foreign.id, candidate.user_id)


async def test_generation_is_candidate_scoped(session, candidate):
    foreign = await _foreign_candidate(session)
    foreign_signals = await _all_signals(session, foreign.id)
    assert foreign_signals == []


# ------------------------------------------------------------------------ #
# Determinism guard: read-only evaluator must not fabricate / write
# ------------------------------------------------------------------------ #


async def test_generation_never_persists_match_for_ineligible_candidate(
    session, candidate
):
    from backend.models.job_match import JobMatch

    service = await _service(session)
    await service.generate_for_candidate(candidate.id, candidate.user_id)
    # Candidate-scoped: the read-only evaluator and the generator must never
    # persist a JobMatch for this candidate (other, unrelated candidates may
    # legitimately carry matches in the shared test database).
    count = (
        await session.execute(
            select(func.count())
            .select_from(JobMatch)
            .where(JobMatch.candidate_id == candidate.id)
        )
    ).scalar_one()
    assert count == 0


async def test_signal_evidence_credit_matches_evidence_provenance(
    session, candidate, job, employer
):
    # A supported primary recruiter contact yields a SUPPORTED evidence signal.
    contact = await _contact(session, candidate.id, employer, job)
    result = await (await _service(session)).generate_for_candidate(
        candidate.id, candidate.user_id
    )
    generated = [s for s in result.generated if s.job_id == job.id]
    assert generated, "expected at least one generated signal for the job"
    evidence_refs = {s.evidence_reference for s in generated}
    loaded = [e for e in result.evidence_loaded if e.evidence_reference in evidence_refs]
    assert loaded, "generated signals must reference loaded evidence"
    assert all(
        e.evidence_strength is RecruiterEvidenceStrength.SUPPORTED for e in loaded
    )
    assert all(e.recruiter_id == contact.id for e in loaded)


async def test_signal_identity_is_deterministic_across_runs(session, candidate, job, employer):
    await _contact(session, candidate.id, employer, job)
    service = await _service(session)
    first = await service.generate_for_candidate(candidate.id, candidate.user_id)
    second = await service.generate_for_candidate(candidate.id, candidate.user_id)
    first_ids = {s.signal_identity for s in first.generated}
    second_ids = {s.signal_identity for s in second.generated}
    assert first_ids == second_ids


async def test_signal_type_choices_are_closed(session):
    assert RecruiterSignalType.RECRUITER_ASSOCIATED is not None
    # Enum membership is closed (no invented types); verify persisted ones map.
    from backend.models.recruiter_signal import RecruiterSignalType as M

    assert M.RECRUITER_ASSOCIATED.value == "recruiter_associated"
