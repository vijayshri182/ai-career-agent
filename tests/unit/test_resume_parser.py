"""Resume parser tests."""

from io import BytesIO

import pytest
from docx import Document

from backend.services.parser import BasicResumeParser


def _docx_bytes(text: str) -> bytes:
    doc = Document()
    doc.add_paragraph(text)
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


@pytest.mark.asyncio
async def test_basic_parser_extracts_email_phone_and_skills():
    parser = BasicResumeParser()
    text = """
    John Doe
    john.doe@example.com
    +91 98765 43210
    Java, Spring Boot, Kubernetes, AWS
    """
    content = _docx_bytes(text)
    data = await parser.parse(content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert data.email == "john.doe@example.com"
    assert data.phone is not None
    assert "Java" in data.skills
    assert "Spring Boot" in data.skills


@pytest.mark.asyncio
async def test_parser_rejects_unsupported_type():
    parser = BasicResumeParser()
    with pytest.raises(ValueError):
        await parser.parse(b"text", "text/plain")
