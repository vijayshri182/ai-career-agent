"""Resume parser abstraction."""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedResumeData:
    """Structured extraction result for a resume."""

    name: str | None = None
    summary: str | None = None
    email: str | None = None
    phone: str | None = None
    skills: list[str] = field(default_factory=list)
    experiences: list[dict[str, Any]] = field(default_factory=list)
    educations: list[dict[str, Any]] = field(default_factory=list)
    certifications: list[dict[str, Any]] = field(default_factory=list)
    job_titles: list[str] = field(default_factory=list)
    companies: list[str] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "summary": self.summary,
            "email": self.email,
            "phone": self.phone,
            "skills": self.skills,
            "experiences": self.experiences,
            "educations": self.educations,
            "certifications": self.certifications,
            "job_titles": self.job_titles,
            "companies": self.companies,
            "technologies": self.technologies,
            "raw_text": self.raw_text,
        }


class ResumeParser(ABC):
    """Interface for resume parsers."""

    @abstractmethod
    async def parse(self, content: bytes, content_type: str) -> ParsedResumeData:
        """Parse resume bytes into structured data."""


class PlainTextExtractor:
    """Extract text from PDF and DOCX files."""

    async def extract(self, content: bytes, content_type: str) -> str:
        if content_type == "application/pdf":
            return self._extract_pdf(content)
        if content_type in {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        }:
            return self._extract_docx(content)
        raise ValueError(f"Unsupported content type: {content_type}")

    def _extract_pdf(self, content: bytes) -> str:
        try:
            import pdfplumber
        except ImportError as exc:
            raise RuntimeError("pdfplumber is required for PDF parsing") from exc
        text = ""
        with pdfplumber.open(BytesIO(content)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text

    def _extract_docx(self, content: bytes) -> str:
        try:
            from docx import Document
        except ImportError as exc:
            raise RuntimeError("python-docx is required for DOCX parsing") from exc
        document = Document(BytesIO(content))
        return "\n".join(p.text for p in document.paragraphs)


class BasicResumeParser(ResumeParser):
    """Rule-based parser for Phase 1. LLM parser can be swapped in later."""

    def __init__(self) -> None:
        self.extractor = PlainTextExtractor()

    async def parse(self, content: bytes, content_type: str) -> ParsedResumeData:
        text = await self.extractor.extract(content, content_type)
        data = ParsedResumeData(raw_text=text[:20000])
        data.email = self._extract_email(text)
        data.phone = self._extract_phone(text)
        data.skills = self._extract_skills(text)
        data.technologies = data.skills
        data.companies = self._extract_companies(text)
        data.job_titles = self._extract_titles(text)
        return data

    def _extract_email(self, text: str) -> str | None:
        match = re.search(r"[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}", text)
        return match.group(0) if match else None

    def _extract_phone(self, text: str) -> str | None:
        match = re.search(r"[\+]?[0-9\s\-\(\)]{10,20}", text)
        return match.group(0).strip() if match else None

    def _extract_skills(self, text: str) -> list[str]:
        # Simple keyword spotting for common technologies.
        keywords = [
            "Java", "Spring Boot", "Microservices", "Kafka", "RabbitMQ", "Angular",
            "Docker", "Kubernetes", "AWS", "CPQ", "PIM", "Order Management",
            "OSS/BSS", "DevOps", "Generative AI", "Python", "FastAPI", "React",
        ]
        found = []
        lower = text.lower()
        for kw in keywords:
            if kw.lower() in lower:
                found.append(kw)
        return found

    def _extract_companies(self, text: str) -> list[str]:
        # Placeholder: no reliable rule-based company extraction.
        return []

    def _extract_titles(self, text: str) -> list[str]:
        # Placeholder.
        return []


class LLMResumeParser(ResumeParser):
    """Stub for future LLM-based parser."""

    async def parse(self, content: bytes, content_type: str) -> ParsedResumeData:
        raise NotImplementedError("LLM parser will be implemented in a later phase")


from io import BytesIO  # noqa: E402
