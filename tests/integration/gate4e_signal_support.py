"""Shared fixtures/helpers for the CP18-CP25 Gate 4E recruiter-signal tests.

Reuses the same persistence wiring the CP15/CP16/CP17 tests use: a real
read-only match evaluator over real persisted state, the real CP16 recorder,
and the real (recording) outreach engine. No mocks, no spies, no network.
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.recruiter_contact import (
    ContactSource,
    ContactSourceType,
    ContactType,
    RecruiterContact,
)
from backend.models.recruiter_signal import RecruiterSignal, RecruiterSignalType


def ingestion_identity(job_id: UUID) -> str:
    return sha256(f"gate4e-signal-flow:{job_id}".encode()).hexdigest()


async def seed_employer(session: AsyncSession):
    from backend.repositories.company import CompanyRepository

    return await CompanyRepository(session).create(
        name="Signal Flow Corp", website_domain="signalflow.example"
    )


async def seed_job(session: AsyncSession, candidate, employer):
    from backend.models.gate4e_ingestion import (
        Gate4eIngestion,
        Gate4eProcessingStatus,
    )
    from backend.models.job import Job
    from backend.models.job_source import JobSource, JobSourceType

    source = JobSource(
        candidate_id=candidate.id,
        name=f"signal-flow-source-{uuid4().hex[:6]}",
        source_type=JobSourceType.JOB_BOARD,
        base_url="https://feed.signalflow.example/jobs.xml",
    )
    session.add(source)
    await session.flush()
    job = Job(
        candidate_id=candidate.id,
        company_id=employer.id,
        source_id=source.id,
        url=f"https://careers.signalflow.example/jobs/{uuid4().hex[:8]}",
        title="Senior Software Engineer",
        location="Remote",
        description="Python and Kubernetes experience required.",
        content_hash=f"signal-flow-{uuid4().hex[:12]}",
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
            ingestion_identity=ingestion_identity(job.id),
            processing_status=Gate4eProcessingStatus.ACCEPTED_VERIFIED,
            verification_status="VERIFIED",
            alert_index=1,
            posting_key=f"signal-flow-key-{uuid4().hex[:6]}",
            company_name=employer.name,
            official_domain="careers.signalflow.example",
            job_title=job.title,
            official_job_url=job.url,
            official_job_id=f"signal-flow-{uuid4().hex[:6]}",
            original_job_url=job.url,
            content_hash=job.content_hash,
            job_id=job.id,
        )
    )
    await session.flush()
    return job


async def seed_contact(
    session: AsyncSession,
    candidate,
    company,
    job,
    *,
    email: str | None = "public.recruiter@signalflow.example",
    verified: bool = True,
    suppressed: bool = False,
):
    source = ContactSource(
        candidate_id=candidate.id,
        company_id=company.id,
        source_type=ContactSourceType.TEAM_PAGE,
        url=f"https://signalflow.example/team/{uuid4().hex[:6]}",
    )
    session.add(source)
    await session.flush()
    contact = RecruiterContact(
        candidate_id=candidate.id,
        company_id=company.id,
        job_id=job.id,
        source_id=source.id,
        full_name="Avery Signal",
        role_title="Talent Acquisition Recruiter",
        public_profile_url=f"https://linkedin.example/in/avery-signal-{uuid4().hex[:6]}",
        email=email,
        confidence_score=88 if verified else 40,
        contact_type=ContactType.VERIFIED if verified else ContactType.GUESSED,
        is_suppressed=suppressed,
    )
    session.add(contact)
    await session.flush()
    return contact


async def build_quality_service(session: AsyncSession):
    from backend.repositories.audit import AuditRepository
    from backend.repositories.candidate import CandidateRepository
    from backend.repositories.recruiter_contact import (
        ContactSourceRepository,
        RecruiterContactRepository,
    )
    from backend.repositories.recruiter_signal import RecruiterSignalRepository
    from backend.services.recruiter_signal_quality import RecruiterSignalQualityService

    return RecruiterSignalQualityService(
        signal_repo=RecruiterSignalRepository(session),
        contact_repo=RecruiterContactRepository(session),
        source_repo=ContactSourceRepository(session),
        candidate_repo=CandidateRepository(session),
        audit_repo=AuditRepository(session),
    )


async def build_recorder(session: AsyncSession):
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


async def build_generation_service(session: AsyncSession):
    from backend.repositories.audit import AuditRepository
    from backend.repositories.candidate import CandidateRepository
    from backend.repositories.experience import ExperienceRepository
    from backend.repositories.gate4e_ingestion import Gate4eIngestionRepository
    from backend.repositories.job import JobRepository
    from backend.repositories.recruiter_contact import (
        ContactSourceRepository,
        RecruiterContactRepository,
    )
    from backend.repositories.recruiter_signal import RecruiterSignalRepository
    from backend.repositories.skill import SkillRepository
    from backend.services.gate4e_eligibility import Gate4eEligibilityService
    from backend.services.gate4e_match_evaluation import Gate4eReadOnlyMatchEvaluator
    from backend.services.recruiter_signal_generation import (
        RecruiterSignalGenerationService,
    )

    eligibility = Gate4eEligibilityService(
        ingestion_repo=Gate4eIngestionRepository(session)
    )
    evaluator = Gate4eReadOnlyMatchEvaluator(
        eligibility=eligibility,
        candidate_repo=CandidateRepository(session),
        job_repo=JobRepository(session),
        skill_repo=SkillRepository(session),
        experience_repo=ExperienceRepository(session),
    )
    return RecruiterSignalGenerationService(
        evaluator=evaluator,
        job_repo=JobRepository(session),
        contact_repo=RecruiterContactRepository(session),
        source_repo=ContactSourceRepository(session),
        signal_repo=RecruiterSignalRepository(session),
        candidate_repo=CandidateRepository(session),
        recorder=await build_recorder(session),
        audit_repo=AuditRepository(session),
    )


async def generate_outreach_signals(
    session: AsyncSession, candidate, user_id
) -> list[RecruiterSignal]:
    service = await build_generation_service(session)
    result = await service.generate_for_candidate(candidate.id, user_id)
    assert result.generated, "expected generated signals"
    return result.generated


async def build_approval_service(session: AsyncSession):
    from backend.repositories.approval import ApprovalDecisionRepository, ApprovalRepository
    from backend.repositories.audit import AuditRepository
    from backend.repositories.candidate import CandidateRepository
    from backend.repositories.company import CompanyRepository
    from backend.repositories.job import JobRepository
    from backend.repositories.recruiter_contact import RecruiterContactRepository
    from backend.repositories.recruiter_signal import RecruiterSignalRepository
    from backend.services.recruiter_signal_approval import RecruiterSignalApprovalService

    return RecruiterSignalApprovalService(
        signal_repo=RecruiterSignalRepository(session),
        contact_repo=RecruiterContactRepository(session),
        job_repo=JobRepository(session),
        company_repo=CompanyRepository(session),
        candidate_repo=CandidateRepository(session),
        approval_repo=ApprovalRepository(session),
        decision_repo=ApprovalDecisionRepository(session),
        audit_repo=AuditRepository(session),
    )


async def build_prep_service(session: AsyncSession):
    from backend.repositories.audit import AuditRepository
    from backend.repositories.candidate import CandidateRepository
    from backend.repositories.certification import CertificationRepository
    from backend.repositories.company import CompanyRepository
    from backend.repositories.education import EducationRepository
    from backend.repositories.experience import ExperienceRepository
    from backend.repositories.job import JobRepository
    from backend.repositories.job_match import JobMatchRepository
    from backend.repositories.recruiter_contact import RecruiterContactRepository
    from backend.repositories.recruiter_signal import RecruiterSignalRepository
    from backend.repositories.skill import SkillRepository
    from backend.services.recruiter_signal_outreach_prep import (
        RecruiterSignalOutreachPrepService,
    )

    return RecruiterSignalOutreachPrepService(
        candidate_repo=CandidateRepository(session),
        signal_repo=RecruiterSignalRepository(session),
        contact_repo=RecruiterContactRepository(session),
        job_repo=JobRepository(session),
        company_repo=CompanyRepository(session),
        skill_repo=SkillRepository(session),
        experience_repo=ExperienceRepository(session),
        education_repo=EducationRepository(session),
        certification_repo=CertificationRepository(session),
        match_repo=JobMatchRepository(session),
        audit_repo=AuditRepository(session),
        approval_service=await build_approval_service(session),
    )


async def load_signal(
    session: AsyncSession, candidate_id: UUID, signal_identity: str
) -> RecruiterSignal:
    from backend.repositories.recruiter_signal import RecruiterSignalRepository

    signal = await RecruiterSignalRepository(session).find_by_identity(
        candidate_id, signal_identity
    )
    assert signal is not None, "signal must exist"
    return signal


def outreach_candidate(generated: list) -> str | None:
    """Return the signal identity of the outreach-candidate signal, if any."""
    for item in generated:
        if item.signal_type is RecruiterSignalType.RECRUITER_OUTREACH_CANDIDATE:
            return item.signal_identity
    return None
