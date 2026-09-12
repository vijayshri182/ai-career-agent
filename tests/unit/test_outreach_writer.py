"""Unit tests for the deterministic, fact-grounded outreach writer."""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from backend.models.candidate import (
    Candidate,
    CandidateSkill,
    Certification,
    Education,
    Experience,
)
from backend.models.company import Company
from backend.models.job import Job
from backend.models.recruiter_contact import ContactType, RecruiterContact
from backend.services.application_prep import ProfileFacts
from backend.services.outreach_writer import (
    ContactGroundedValidator,
    DeterministicOutreachWriter,
)


def _candidate(**overrides) -> Candidate:
    base = Candidate(
        user_id=uuid4(),
        full_name="Test Candidate",
        headline="Senior Engineer",
        current_role="Engineering Lead",
        target_role="Senior Software Engineer",
        total_experience_years=12,
        expected_compensation_amount=50,
        expected_compensation_currency="USD",
    )
    base.__dict__.update(overrides)
    return base


def _contact(**overrides) -> RecruiterContact:
    base = RecruiterContact(
        candidate_id=uuid4(),
        company_id=uuid4(),
        source_id=uuid4(),
        full_name="Alex Rivera",
        role_title="Talent Acquisition Recruiter",
        public_profile_url="https://careers.test/profile/alex",
        email="alex@acme.test",
        contact_type=ContactType.VERIFIED,
        confidence_score=95,
    )
    base.__dict__.update(overrides)
    return base


def _job(title: str = "Senior Software Engineer") -> Job:
    return Job(
        candidate_id=uuid4(),
        company_id=uuid4(),
        source_id=uuid4(),
        url="https://careers.test/jobs/1",
        title=title,
        location="Bangalore, India",
        description="Qualifications:\n- 5+ years of software engineering\n",
        content_hash="hash-sse",
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )


def _company() -> Company:
    return Company(name="Acme Networks", website_domain="acme.test")


def _rich_facts(job: Job | None = None, company: Company | None = None) -> ProfileFacts:
    return ProfileFacts(
        candidate=_candidate(),
        skills=[
            CandidateSkill(candidate_id=uuid4(), name="Python"),
            CandidateSkill(candidate_id=uuid4(), name="Kubernetes"),
        ],
        experiences=[
            Experience(
                candidate_id=uuid4(),
                company_name="Telco Systems",
                title="Engineering Lead",
                start_date=date(2018, 1, 1),
                is_current=True,
                technologies=["Python", "Kubernetes"],
                domain="Telecom BSS",
            )
        ],
        educations=[
            Education(candidate_id=uuid4(), institution="State University", degree="B.Tech")
        ],
        certifications=[Certification(candidate_id=uuid4(), name="CKAD")],
        job=(job or _job()),
        company=(company or _company()),
    )


@pytest.mark.asyncio
async def test_generated_initial_draft_is_fact_grounded() -> None:
    facts = _rich_facts()
    contact = _contact()
    writer = DeterministicOutreachWriter()

    generated = await writer.generate(facts, contact)
    assert generated.subject == "Application for Senior Software Engineer at Acme Networks"
    assert "Alex Rivera" in generated.body
    assert generated.subject and generated.body.strip()
    assert generated.fact_sources, "fact sources must be recorded"

    flagged = await writer.validate(generated, facts, contact)
    assert flagged == [], f"generated draft flagged: {flagged}"


@pytest.mark.asyncio
async def test_generated_draft_without_job_passes_grounding() -> None:
    facts = ProfileFacts(candidate=_candidate())
    contact = _contact()
    writer = DeterministicOutreachWriter()

    generated = await writer.generate(facts, contact)
    assert generated.subject.startswith("Introduction from")
    flagged = await writer.validate(generated, facts, contact)
    assert flagged == [], f"no-job draft flagged: {flagged}"


@pytest.mark.asyncio
async def test_follow_up_is_reply_prefixed_and_grounded() -> None:
    facts = _rich_facts()
    contact = _contact()
    writer = DeterministicOutreachWriter()

    parent = await writer.generate(facts, contact)
    follow_up = await writer.generate_follow_up(
        facts, contact, parent_subject=parent.subject
    )
    assert follow_up.subject == f"Re: {parent.subject}"
    flagged = await writer.validate(follow_up, facts, contact)
    assert flagged == [], f"follow-up draft flagged: {flagged}"


def test_validator_accepts_verified_contact_identity() -> None:
    facts = ProfileFacts(candidate=_candidate())
    contact = _contact()
    validator = ContactGroundedValidator(contact=contact)
    sentence = f"Dear {contact.full_name}, I am writing to you about this role."
    assert validator.validate(sentence, facts) == []


def test_validator_flags_invented_company() -> None:
    facts = _rich_facts()
    contact = _contact()
    validator = ContactGroundedValidator(contact=contact)
    sentence = "I led the rollout at SynthCorp Industries last quarter."
    flagged = validator.validate(sentence, facts)
    assert any("SynthCorp" in line for line in flagged)


def test_validator_flags_known_skill_that_is_not_in_profile() -> None:
    facts = _rich_facts()
    contact = _contact()
    validator = ContactGroundedValidator(contact=contact)
    flagged = validator.validate("I am an expert in Kafka streaming pipelines.", facts)
    assert any("Kafka" in line for line in flagged)
