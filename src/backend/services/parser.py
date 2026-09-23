"""Resume parser abstraction."""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from backend.services.skills import SKILLS, SkillExtractor

_MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_DATE_BLOCK_RE = re.compile(
    rf"{_MONTH}\s+\d{{4}}\s*[-–—]+\s*"
    rf"(?:{_MONTH}\s+\d{{4}}|present)",
    re.IGNORECASE,
)
_YEARS_EXPERIENCE_RE = re.compile(
    r"(\d{1,2})\s*\+?\s*(?:years|yrs)\s+of\s+(?:experience|exp|work|industry)",
    re.IGNORECASE,
)
_NAME_RUN_RE = re.compile(r"^([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+)+)")
_SUMMARY_HEADER_RE = re.compile(
    r"^\s*(?:profile|professional|career)?\s*summary\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_BULLET_CHARS = "\u2022\u25aa\u25cf\u25a0\u2023\u2043\u2666\u2043*"
_LOCATION_MARKERS = frozenset({"location", "address"})

# Upper-case header/labels that must never be treated as personal data.
_NON_NAME_LABELS = frozenset(
    {
        "mobile",
        "phone",
        "tel",
        "cell",
        "email",
        "e-mail",
        "linkedin",
        "github",
        "address",
        "www",
        "website",
        "profile",
        "contact",
        "skype",
        "id",
    }
)
_SECTION_LINES = frozenset(
    {
        "work experience",
        "career timeline",
        "projects",
        "personal details",
        "languages known",
        "education",
        "technical skills",
        "core competencies",
        "profile summary",
        "trainings & certifications",
        "trainings and certifications",
        "summary",
        "location",
        "achievements",
        "skills",
        "experience",
        "objective",
        "professional summary",
        "employment history",
        "key skills",
        "additional information",
    }
)
_COUNTRY_NAMES = frozenset(
    {
        "india",
        "usa",
        "u.s.",
        "u.s.a.",
        "united states",
        "uk",
        "united kingdom",
        "canada",
        "australia",
        "germany",
        "france",
        "netherlands",
        "singapore",
        "uae",
        "united arab emirates",
        "morocco",
        "malaysia",
        "ghana",
        "mozambique",
        "iran",
        "ireland",
        "japan",
        "china",
        "new zealand",
        "switzerland",
    }
)


@dataclass
class ParsedResumeData:
    """Structured extraction result for a resume."""

    name: str | None = None
    headline: str | None = None
    current_role: str | None = None
    total_experience_years: int | None = None
    current_location: dict[str, Any] | None = None
    summary: str | None = None
    email: str | None = None
    phone: str | None = None
    skills: list[str] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)
    experiences: list[dict[str, Any]] = field(default_factory=list)
    educations: list[dict[str, Any]] = field(default_factory=list)
    certifications: list[dict[str, Any]] = field(default_factory=list)
    job_titles: list[str] = field(default_factory=list)
    companies: list[str] = field(default_factory=list)
    confidence_score: int | None = None
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "headline": self.headline,
            "current_role": self.current_role,
            "total_experience_years": self.total_experience_years,
            "current_location": self.current_location,
            "summary": self.summary,
            "email": self.email,
            "phone": self.phone,
            "skills": self.skills,
            "technologies": self.technologies,
            "experiences": self.experiences,
            "educations": self.educations,
            "certifications": self.certifications,
            "job_titles": self.job_titles,
            "companies": self.companies,
            "confidence_score": self.confidence_score,
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
    """Rule-based deterministic parser.

    Skills reuse the shared ``SkillExtractor`` vocabulary; profile scalars are
    derived from deterministic line/header heuristics so every extraction is
    reproducible. ``experiences``/``educations``/``certifications`` are Phase-2
    and intentionally left empty.
    """

    def __init__(self) -> None:
        self.extractor = PlainTextExtractor()
        self._skills = SkillExtractor()

    async def parse(self, content: bytes, content_type: str) -> ParsedResumeData:
        text = await self.extractor.extract(content, content_type)
        data = ParsedResumeData(raw_text=text[:20000])
        data.email = self._extract_email(text)
        data.phone = self._extract_phone(text)
        data.name = self._extract_name(text)
        data.headline = self._extract_headline(text)
        data.current_location = self._extract_location(text)
        data.current_role = self._extract_current_role(text)
        data.summary = self._extract_summary(text)
        data.total_experience_years = self._extract_experience_years(text)
        skills = sorted(self._skills.extract(text))
        data.skills = [SKILLS.get(name, name) for name in skills]
        data.technologies = data.skills
        data.confidence_score = self._confidence(data)
        return data

    @staticmethod
    def _extract_email(text: str) -> str | None:
        match = re.search(r"[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}", text)
        return match.group(0) if match else None

    @staticmethod
    def _extract_phone(text: str) -> str | None:
        match = re.search(r"[\+]?[0-9\s\-\(\)]{10,20}", text)
        return match.group(0).strip() if match else None

    def _extract_name(self, text: str) -> str | None:
        for line in [ln.strip() for ln in text.splitlines() if ln.strip()][:12]:
            match = _NAME_RUN_RE.match(line.lstrip(_BULLET_CHARS))
            if not match:
                continue
            words: list[str] = []
            for word in match.group(1).split():
                if word.lower().rstrip(".") in _NON_NAME_LABELS or any(
                    c.isdigit() for c in word
                ):
                    break
                words.append(word)
            if not 2 <= len(words) <= 4:
                continue
            candidate = " ".join(words)
            if candidate.lower() in _SECTION_LINES or "|" in candidate or "@" in candidate:
                continue
            return candidate
        return None

    def _extract_headline(self, text: str) -> str | None:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        for i, line in enumerate(lines[:25]):
            if "|" not in line or "@" in line:
                continue
            segments = [s.strip() for s in line.split("|")]
            if len(segments) < 2 or any(not s for s in segments):
                continue
            parts = [line]
            for following in lines[i + 1 : i + 3]:
                if "|" in following:
                    parts.append(following)
            headline = " ".join(parts)
            if 10 <= len(headline) <= 300:
                return headline
        return None

    @staticmethod
    def _is_section_heading(line: str) -> bool:
        if len(line) > 60:
            return False
        if not (line.isupper() or line.upper() == line):
            return False
        return len(line.split()) >= 2

    def _extract_summary(self, text: str) -> str | None:
        match = _SUMMARY_HEADER_RE.search(text)
        if not match:
            return None
        bullets: list[str] = []
        for line in text[match.end() :].splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if self._is_section_heading(stripped) or stripped.lower() in _SECTION_LINES:
                break
            if len(stripped) < 3:
                continue
            cleaned = stripped.lstrip(_BULLET_CHARS).strip()
            if cleaned:
                bullets.append(cleaned)
            if len(bullets) >= 12:
                break
        return "\n".join(bullets) if bullets else None

    @staticmethod
    def _extract_experience_years(text: str) -> int | None:
        match = _YEARS_EXPERIENCE_RE.search(text)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    @staticmethod
    def _extract_location(text: str) -> dict[str, Any] | None:
        lines = text.splitlines()
        for i, line in enumerate(lines):
            marker = line.strip().lower().rstrip(":")
            if marker not in _LOCATION_MARKERS:
                continue
            for raw in lines[i + 1 : i + 3]:
                candidate = raw.strip()
                if not candidate or "|" in candidate:
                    continue
                candidate = re.sub(r"\b\d{5,6}\b", "", candidate).strip(" ,;.-")
                if not 2 <= len(candidate) <= 80:
                    continue
                parsed = BasicResumeParser._city_country(candidate)
                if parsed:
                    return parsed
        return None

    @staticmethod
    def _city_country(value: str) -> dict[str, Any] | None:
        parts = [p.strip() for p in value.split(",") if p.strip()]
        if not parts:
            return None
        city = parts[0]
        country: str | None = None
        for part in parts[1:]:
            lowered = part.lower()
            if lowered in _COUNTRY_NAMES:
                country = part
                break
            matches = [p for p in lowered.split() if p in _COUNTRY_NAMES]
            if matches:
                country = matches[-1]
                break
        return {"city": city, "country": country} if city else None

    def _extract_current_role(self, text: str) -> str | None:
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if "present" not in line.lower() or not _DATE_BLOCK_RE.search(line):
                continue
            role = self._title_after(lines, i + 1)
            if role:
                return role
        for i, line in enumerate(lines):
            if not _DATE_BLOCK_RE.search(line):
                continue
            role = self._title_after(lines, i + 1)
            if role:
                return role
        return None

    @staticmethod
    def _title_after(lines: list[str], start: int) -> str | None:
        for line in lines[start : start + 3]:
            candidate = line.strip()
            if not candidate:
                continue
            lower = candidate.lower()
            if lower in _SECTION_LINES or _DATE_BLOCK_RE.search(candidate):
                continue
            if "|" in candidate or len(candidate) > 100:
                continue
            if not any(c.islower() for c in candidate):
                continue
            return candidate
        return None

    @staticmethod
    def _confidence(data: ParsedResumeData) -> int:
        checks: list[tuple[bool, int]] = [
            (bool(data.name), 15),
            (bool(data.email), 10),
            (bool(data.phone), 10),
            (bool(data.headline), 10),
            (bool(data.current_role), 10),
            (bool(data.summary), 15),
            (data.total_experience_years is not None, 10),
            (bool(data.current_location), 10),
            (bool(data.skills), 10),
        ]
        return sum(weight for present, weight in checks if present)


class LLMResumeParser(ResumeParser):
    """Stub for future LLM-based parser."""

    async def parse(self, content: bytes, content_type: str) -> ParsedResumeData:
        raise NotImplementedError("LLM parser will be implemented in a later phase")


from io import BytesIO  # noqa: E402
