"""Phase-1 PostgreSQL regression: upload -> parse -> apply -> fresh-read.

The Phase-1 parser replaces the 17-keyword matcher with the shared
``SkillExtractor`` vocabulary and produces a deterministic rich profile
(name, headline, current_role, summary, total_experience_years,
current_location) instead of only email/phone/skills. It must persist those
fields through ``CandidateRepository`` (whose ``current_location`` column is an
encrypted JSON blob read through a decrypting property) without raising
Fernet ``InvalidToken``, keep re-parse/applied-fields state, never clobber
user-edited fields on re-apply, keep skill insertion idempotent, and keep the
released email/phone encryption layers intact.

The full scenario is PostgreSQL-specific and is skipped unless
``TEST_POSTGRESQL_URL`` points at a disposable PostgreSQL database. The
column/layer invariants below always run so the default suite still guards
the declaration and the current_location read path.
"""

import os
from io import BytesIO
from uuid import uuid4

import pytest
import pytest_asyncio
from docx import Document
from fastapi import UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

from backend.core.config import get_settings
from backend.db.engine import make_session_factory
from backend.models import *  # noqa: F401, F403
from backend.models.candidate import Candidate
from backend.models.resume import ResumeType
from backend.repositories.audit import AuditRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.resume import (
    ParsedResumeRepository,
    ResumeRepository,
    ResumeVersionRepository,
)
from backend.repositories.skill import SkillRepository
from backend.repositories.user import UserRepository
from backend.schemas.resume import ResumeCreate
from backend.services.parser import BasicResumeParser
from backend.services.resume import ResumeService
from backend.services.storage import LocalFileStorage

TEST_URL = os.environ.get("TEST_POSTGRESQL_URL", "")
_SKIP_REASON = "TEST_POSTGRESQL_URL unset; PostgreSQL regression test skipped"

# Mirrors the structure of the real reference resume.
REAL_RESUME_TEXT = """EMAIL vijayshri182@gmail.com
VIJAY SHRIVASTAVA MOBILE +91 9148975538
LINKEDIN vijay-shrivastava-a29a1313
Engineering Leader | Telecom BSS/OSS | Product Engineering | AI-Enabled
LOCATION
Transformation | Agile Delivery
Bangalore, 560036
Engineering & Technology Leader with 20+ years of experience driving technology transformation.
PROFILE SUMMARY
Senior Engineering & Technology Leader with expertise in AI-enabled engineering, product engineering and Agile delivery.
Drove practical adoption of Generative AI and AI-assisted engineering across code understanding and automation.
Strong expertise in performance engineering, troubleshooting, profiling and root-cause analysis.
Experienced in leading cross-functional engineering teams and partnering with Product, QA and Engineering.
CORE COMPETENCIES
Technology Strategy & Roadmap
Agile / Scrum Leadership
TECHNICAL SKILLS
Netcracker Platforms: CPQ, PIM, Order Management
Programming & Frameworks: Java, J2EE, Spring, Hibernate, Angular
Cloud & Infrastructure: AWS, Linux, Kubernetes, HA Proxy
Middleware & Messaging: Kafka, Hadoop, HBase
Databases: Oracle, MySQL, PostgreSQL, Redis
Build DevOps & CI/CD: Jenkins, CI/CD Pipelines
Testing & Monitoring: Postman, Application Logs & Monitoring Tools
AI-Assisted Engineering: Generative AI
Project & Collaboration: Jira, Confluence
EDUCATION
2005: B.E. (Electronic and Telecommunication)
TRAININGS & CERTIFICATIONS
Management Program on People and Culture at XLRI in 2019
PMP Certification Training in 2016
CAREER TIMELINE
2024-Present | Netcracker
2019-2024 | Pelatro
WORK EXPERIENCE
Jul 2024-Present | Netcracker Technology Pvt. Ltd.
Senior Technical Manager
Spearheading engineering delivery for JSAT, leading a 40-member team.
Driving an AI-enabled SDLC across CPQ, PIM, Order Management, Kafka, Kubernetes and AWS.
Mentoring and developing 20 engineers through technical coaching.
Jun 2019-Jun 2024 | Pelatro Solutions Ltd.
Roadmap Manager
Led product roadmap and reporting across Angular and Spring projects.
PERSONAL DETAILS
Languages Known: English and Hindi
"""

APPLIED_FIELDS = {
    "full_name",
    "email",
    "phone",
    "headline",
    "current_role",
    "summary",
    "total_experience_years",
    "current_location",
}

EXPECTED_SKILLS = {
    "Java",
    "Kubernetes",
    "Apache Kafka",
    "AWS",
    "Agile",
    "Scrum",
    "PostgreSQL",
    "Jenkins",
    "Linux",
    "Generative AI",
}


def test_model_current_location_column_has_capacity() -> None:
    """Model invariant: encrypted location JSON column must fit ciphertext."""
    column = Candidate.__table__.c.current_location_json
    assert column.type.length is not None
    assert column.type.length >= 256


@pytest.mark.asyncio
async def test_current_location_roundtrip_with_fresh_read(session, engine) -> None:
    """current_location stored with the balanced layer reads back as plaintext."""
    user = await UserRepository(session).create_user(
        f"loc-rt-{uuid4().hex[:8]}@example.com", "StrongP@ssw0rd!9"
    )
    location = {"city": "Bangalore", "country": "India"}
    candidate = await CandidateRepository(session).create_for_user(
        user.id,
        email=f"locr-{uuid4().hex[:8]}@example.com",
        current_location=location,
    )
    assert candidate.current_location == location
    await session.commit()

    factory = make_session_factory(engine)
    async with factory() as fresh:
        reloaded = await fresh.get(Candidate, candidate.id)
        assert reloaded is not None
        assert reloaded.current_location == location


def _docx_bytes(text: str) -> tuple[bytes, str]:
    doc = Document()
    for line in text.splitlines():
        doc.add_paragraph(line)
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


async def _make_service(pg_session) -> ResumeService:
    settings = get_settings()
    return ResumeService(
        ResumeRepository(pg_session),
        ResumeVersionRepository(pg_session),
        ParsedResumeRepository(pg_session),
        AuditRepository(pg_session),
        CandidateRepository(pg_session),
        SkillRepository(pg_session),
        storage=LocalFileStorage(settings),
        parser=BasicResumeParser(),
        settings=settings,
    )


@pytest_asyncio.fixture
async def pg_session():
    engine = create_async_engine(TEST_URL, future=True)
    async with engine.begin() as conn:
        if TEST_URL.startswith("postgresql"):
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        else:
            await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    session_factory = make_session_factory(engine)
    async with session_factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest.mark.skipif(not TEST_URL, reason=_SKIP_REASON)
@pytest.mark.asyncio
async def test_phase1_apply_builds_rich_profile_on_postgresql(pg_session) -> None:
    """Full upload -> parse -> apply -> fresh-read must persist the rich profile."""
    user = await UserRepository(pg_session).create_user(
        f"pg-pc-{uuid4().hex[:8]}@example.com", "StrongP@ssw0rd!9"
    )
    email = f"pgpro-{uuid4().hex[:8]}@example.com"
    candidate = await CandidateRepository(pg_session).create_for_user(
        user.id, email=email, full_name="PG Rich Profile"
    )
    assert candidate.phone is None
    assert candidate.current_location is None
    await pg_session.commit()

    service = await _make_service(pg_session)
    resume = await service.create_resume(
        candidate.id,
        user.id,
        ResumeCreate(name="PG Resume", resume_type=ResumeType.GENERAL),
    )

    content, ctype = _docx_bytes(REAL_RESUME_TEXT)
    await service.upload_resume(
        candidate.id,
        user.id,
        resume.id,
        UploadFile(
            file=BytesIO(content),
            filename="pg_resume.docx",
            headers={"content-type": ctype},
        ),
    )

    parsed = await service.parse_resume(candidate.id, user.id, resume.id)
    assert parsed.confidence_score == 100
    assert parsed.extracted_data["name"] == "VIJAY SHRIVASTAVA"
    assert parsed.extracted_data["email"] == "vijayshri182@gmail.com"
    assert parsed.extracted_data["phone"] == "+91 9148975538"
    assert parsed.extracted_data["current_role"] == "Senior Technical Manager"
    assert parsed.extracted_data["total_experience_years"] == 20
    assert parsed.extracted_data["current_location"] == {
        "city": "Bangalore",
        "country": None,
    }
    assert EXPECTED_SKILLS.issubset(set(parsed.extracted_data["skills"]))

    applied = await service.apply_parsed_resume(candidate.id, user.id, resume.id)
    assert applied.status == "applied"
    assert set(applied.applied_fields) == APPLIED_FIELDS
    await pg_session.commit()

    pg = create_async_engine(TEST_URL, future=True)
    try:
        async with make_session_factory(pg)() as fresh_session:
            reloaded = await fresh_session.get(Candidate, candidate.id)
            assert reloaded is not None
            assert reloaded.full_name == "VIJAY SHRIVASTAVA"
            assert reloaded.email == "vijayshri182@gmail.com"
            assert reloaded.phone == "+91 9148975538"
            assert reloaded.headline == (
                "Engineering Leader | Telecom BSS/OSS | Product Engineering "
                "| AI-Enabled Transformation | Agile Delivery"
            )
            assert reloaded.current_role == "Senior Technical Manager"
            assert reloaded.total_experience_years == 20
            assert reloaded.current_location == {"city": "Bangalore", "country": None}
            assert "AI-enabled engineering" in (reloaded.summary or "")

            skill_names = {
                skill.name for skill in await SkillRepository(fresh_session).list_for_candidate(candidate.id)
            }
            assert EXPECTED_SKILLS.issubset(skill_names)
            assert len(skill_names) == len({name.lower() for name in skill_names})

        applied_events = await AuditRepository(pg_session).list_for_candidate(
            candidate.id, event_type="RESUME_PARSED_APPLIED"
        )
        assert applied_events
        first = applied_events[0].event_metadata or {}
        assert set(first.get("profile_fields", [])).issubset(APPLIED_FIELDS)
        assert first.get("skills_added")
    finally:
        await pg.dispose()

    # User keeps manual edits: re-parse must not reset applied-fields state,
    # and re-apply must not clobber the overridden name or add skills again.
    await CandidateRepository(pg_session).update_candidate(candidate, full_name="User Override")
    await pg_session.commit()

    re_parsed = await service.parse_resume(candidate.id, user.id, resume.id)
    assert re_parsed.status == "pending"
    assert set(re_parsed.applied_fields) == APPLIED_FIELDS

    re_applied = await service.apply_parsed_resume(candidate.id, user.id, resume.id)
    assert re_applied.status == "applied"
    assert set(re_applied.applied_fields) == APPLIED_FIELDS

    skill_count_before = len(await SkillRepository(pg_session).list_for_candidate(candidate.id))
    assert skill_count_before == len(skill_names)
    await pg_session.commit()

    pg2 = create_async_engine(TEST_URL, future=True)
    try:
        async with make_session_factory(pg2)() as fresh_session:
            reloaded2 = await fresh_session.get(Candidate, candidate.id)
            assert reloaded2 is not None
            assert reloaded2.full_name == "User Override"
            assert reloaded2.current_location == {"city": "Bangalore", "country": None}
            assert reloaded2.phone == "+91 9148975538"
            assert (
                len(await SkillRepository(fresh_session).list_for_candidate(candidate.id))
                == skill_count_before
            )
    finally:
        await pg2.dispose()
