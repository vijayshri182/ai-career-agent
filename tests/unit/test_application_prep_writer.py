"""Unit tests for application material preparation (deterministic, fact-grounded)."""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from backend.models.application import (
    AnswerStatus,
    DocumentType,
    QuestionCategory,
)
from backend.models.candidate import (
    Candidate,
    CandidateSkill,
    Certification,
    Education,
    Experience,
)
from backend.models.company import Company
from backend.models.job import Job
from backend.models.job_match import JobMatch
from backend.models.resume import Resume, ResumeType, ResumeVersion
from backend.services.application_prep import (
    DeterministicApplicationWriter,
    FactGroundingValidator,
    ProfileFacts,
    _resume_type_match,
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


def _job(title: str = "Senior Software Engineer", description: str = "") -> Job:
    return Job(
        candidate_id=uuid4(),
        company_id=uuid4(),
        source_id=uuid4(),
        url="https://careers.test/jobs/1",
        title=title,
        location="Bangalore, India",
        description=description,
        content_hash="hash-sse",
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )


def _company() -> Company:
    return Company(name="Acme Networks", website_domain="acme.test")


def _match(missing_skills: list[str] | None = None) -> JobMatch:
    return JobMatch(
        candidate_id=uuid4(),
        job_id=uuid4(),
        score=85.0,
        confidence=0.9,
        is_match=True,
        matched_skills=["Python", "Kubernetes"],
        missing_skills=missing_skills or [],
        strengths=["Python and Kubernetes match the required skills"],
        rules_version="1.0.0",
        evaluated_at=datetime.now(UTC),
    )


def _rich_facts(match: JobMatch | None = None) -> ProfileFacts:
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
        match=match,
        job=_job(),
        company=_company(),
    )


async def _write() -> DeterministicApplicationWriter:
    writer = DeterministicApplicationWriter()
    # force registry configuration so relationships resolve in tests
    from backend.models.application import Application  # noqa: F401

    return writer


@pytest.mark.asyncio
async def test_prepare_questions_are_fact_grounded() -> None:
    facts = _rich_facts(_match())
    writer = await _write()
    questions = await writer.prepare_content(facts)

    texts = {q.question_text for q in questions}
    assert "Describe your professional experience relevant to this role." in texts
    assert "What are your salary or compensation expectations?" in texts

    by_category = {q.category: q for q in questions}
    assert by_category[QuestionCategory.EXPERIENCE].status == AnswerStatus.AUTO
    assert by_category[QuestionCategory.TECHNICAL].status == AnswerStatus.AUTO
    assert (
        by_category[QuestionCategory.MOTIVATION].status
        == AnswerStatus.REQUIRES_REVIEW
    )

    for question in questions:
        for source in question.fact_sources:
            assert source.ref_id is not None, f"missing ref_id: {source.text}"
            assert source.text, "empty fact source text"


@pytest.mark.asyncio
async def test_compensation_missing_becomes_requires_review() -> None:
    facts = _rich_facts(_match())
    facts.candidate.expected_compensation_amount = None
    writer = await _write()
    questions = await writer.prepare_content(facts)
    compensation = next(
        q for q in questions if q.category == QuestionCategory.COMPENSATION
    )
    assert compensation.status == AnswerStatus.REQUIRES_REVIEW
    assert compensation.answer_text == ""


@pytest.mark.asyncio
async def test_missing_skills_get_requires_review_questions() -> None:
    facts = _rich_facts(_match(missing_skills=["Kafka", "AWS"]))
    writer = await _write()
    questions = await writer.prepare_content(facts)
    technical = [q for q in questions if q.category == QuestionCategory.TECHNICAL]
    missing = [q for q in technical if "missing requirement" in q.question_text]
    assert len(missing) == 2
    assert all(q.status == AnswerStatus.REQUIRES_REVIEW for q in missing)
    assert "Kafka" in missing[0].question_text


@pytest.mark.asyncio
async def test_all_documents_pass_fact_grounding() -> None:
    facts = _rich_facts(_match())
    writer = await _write()
    for doc_type in (
        DocumentType.COVER_LETTER,
        DocumentType.TAILORED_RESUME,
        DocumentType.ANSWERS_SHEET,
    ):
        doc = await writer.generate_document(facts, doc_type)
        flagged = await writer.validate_document(doc, facts)
        assert flagged == [], f"{doc_type} flagged: {flagged}"
        assert doc.content.strip(), f"{doc_type} produced empty content"


@pytest.mark.asyncio
async def test_cover_letter_mentions_job_and_company() -> None:
    facts = _rich_facts(_match())
    writer = await _write()
    doc = await writer.generate_document(facts, DocumentType.COVER_LETTER)
    assert "Acme Networks" in doc.content
    assert "Senior Software Engineer" in doc.content
    assert doc.title == "Cover Letter - Senior Software Engineer"


@pytest.mark.asyncio
async def test_invented_capitalized_claim_is_flagged() -> None:
    facts = _rich_facts(_match())
    validator = FactGroundingValidator()
    sentence = "I led the migration for SynthCorp Systems and owned their rollout."
    flagged = validator.validate(sentence, facts)
    assert any("SynthCorp" in line for line in flagged)


@pytest.mark.asyncio
async def test_known_skill_not_in_profile_is_flagged() -> None:
    facts = _rich_facts(_match())
    validator = FactGroundingValidator()
    flagged = validator.validate(
        "I am an expert in Kafka streaming pipelines.", facts
    )
    assert any("Kafka" in line for line in flagged)


def test_framing_prose_passes() -> None:
    facts = _rich_facts(_match())
    validator = FactGroundingValidator()
    prose = "Dear Hiring Team, I would welcome the opportunity to discuss this role."
    assert validator.validate(prose, facts) == []


def test_generated_answer_with_profile_entity_passes() -> None:
    facts = _rich_facts(_match())
    validator = FactGroundingValidator()
    answer = "My professional background includes Engineering Lead and Python."
    assert validator.validate(answer, facts) == []


def test_resume_type_match_scores() -> None:
    assert _resume_type_match(ResumeType.AI_GENAI, "ai engineer") == 30
    assert (
        _resume_type_match(ResumeType.ENGINEERING_MANAGER, "engineering manager") == 30
    )
    assert _resume_type_match(ResumeType.TECHNICAL_MANAGER, "technical lead") == 30
    assert _resume_type_match(ResumeType.SOLUTION_ARCHITECT, "solution architect") == 30
    assert _resume_type_match(ResumeType.GENERAL, "software engineer") == 10
    assert _resume_type_match(ResumeType.CUSTOM, "software engineer") == 0


def test_profile_facts_entities_are_traceable() -> None:
    facts = _rich_facts(_match())
    refs = facts.entities()
    assert refs
    for ref in refs:
        assert ref.ref_id is not None
        assert ref.text


def _resume(
    resume_type: ResumeType,
    *,
    default: bool = False,
    active_version: bool = True,
) -> Resume:
    resume = Resume(
        candidate_id=uuid4(),
        name=f"Resume {resume_type.value}",
        resume_type=resume_type,
        target_role="Senior Software Engineer",
        is_default=default,
    )
    if active_version:
        version = ResumeVersion(
            resume_id=resume.id,
            version_number=1,
            original_filename="r.pdf",
            storage_backend="local",
            storage_path="/tmp/r.pdf",
            content_type="application/pdf",
            size_bytes=10,
        )
        resume.active_version_id = version.id
        resume.versions = [version]
    return resume


@pytest.mark.asyncio
async def test_facts_require_match_to_skip_missing_skills() -> None:
    """Without a match the writer must not fabricate a skill-gap section."""
    facts = _rich_facts(match=None)
    writer = await _write()
    questions = await writer.prepare_content(facts)
    assert not any(
        "missing requirement" in q.question_text for q in questions
    )


@pytest.mark.asyncio
async def test_resume_selection_prefers_active_default() -> None:
    from backend.services.application_prep import ApplicationPrepService

    service = object.__new__(ApplicationPrepService)
    general = _resume(ResumeType.GENERAL, default=True)
    custom = _resume(ResumeType.CUSTOM, active_version=False)
    selected = await service._select_resume([custom, general], _job("Software Engineer"))
    assert selected is general
