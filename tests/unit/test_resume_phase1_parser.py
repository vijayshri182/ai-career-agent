"""Phase-1 golden tests for the deterministic resume parser.

The fixture mirrors the structure of the real reference resume so the
extraction contract (name, headline, current_role, summary,
total_experience_years, current_location, expanded vocabulary skills,
confidence_score) stays pinned. Experiences/educations/certifications are
Phase-2 and must remain empty.
"""

from io import BytesIO

import pytest
from docx import Document

from backend.services.parser import BasicResumeParser
from backend.services.skills import SKILLS

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

CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _parse_docx(text: str):
    doc = Document()
    for line in text.splitlines():
        doc.add_paragraph(line)
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return BasicResumeParser().parse(buf.read(), CONTENT_TYPE)


@pytest.mark.asyncio
async def test_real_resume_structure_extracts_rich_deterministic_profile():
    data = await _parse_docx(REAL_RESUME_TEXT)

    assert data.name == "VIJAY SHRIVASTAVA"
    assert data.email == "vijayshri182@gmail.com"
    assert data.phone == "+91 9148975538"
    assert (
        data.headline
        == "Engineering Leader | Telecom BSS/OSS | Product Engineering | AI-Enabled Transformation | Agile Delivery"
    )
    assert data.current_role == "Senior Technical Manager"
    assert data.total_experience_years == 20
    assert data.current_location == {"city": "Bangalore", "country": None}

    assert data.summary is not None
    assert "AI-enabled engineering" in data.summary
    assert "cross-functional engineering teams" in data.summary

    # Expanded vocabulary (shared SkillExtractor) rather than the old 17 keywords.
    assert len(data.skills) >= 12
    assert {
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
    }.issubset(set(data.skills))
    # Every emitted skill is a label from the single shared vocabulary.
    assert set(data.skills).issubset(set(SKILLS.values()))

    # Exposure-shaped confidence: every scored field is present.
    assert data.confidence_score == 100

    # Phase 2 fields stay empty by design.
    assert data.experiences == []
    assert data.educations == []
    assert data.certifications == []


@pytest.mark.asyncio
async def test_sparse_resume_keeps_low_confidence():
    text = "jane.sparse@example.com"
    data = await _parse_docx(text)
    assert data.email == "jane.sparse@example.com"
    assert data.name is None
    assert data.headline is None
    assert data.current_role is None
    assert data.summary is None
    assert data.total_experience_years is None
    assert data.current_location is None
    assert data.skills == []
    assert data.confidence_score is not None and 0 <= data.confidence_score <= 20


@pytest.mark.asyncio
async def test_label_only_header_lines_never_become_name():
    text = "EMAIL someone@example.com\nLINKEDIN someone\nLOCATION\nBangalore, India"
    data = await _parse_docx(text)
    assert data.name is None
    assert data.current_location == {"city": "Bangalore", "country": "India"}


@pytest.mark.asyncio
async def test_confidence_scales_with_extracted_fields():
    data = await _parse_docx("Jane Roe\njane.roe@example.com\n+91 90000 00000")
    assert data.name == "Jane Roe"
    # name(15) + email(10) + phone(10) -> skills absent -> 35
    assert data.confidence_score == 35


@pytest.mark.asyncio
async def test_parse_rejects_unsupported_type():
    parser = BasicResumeParser()
    with pytest.raises(ValueError):
        await parser.parse(b"text", "text/plain")
