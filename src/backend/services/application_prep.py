"""Application material preparation.

Deterministic, fact-grounded generation of application materials from a
candidate's verified profile plus the explainable match output. Nothing here
invents facts: every sentence in generated documents and every auto-generated
answer is assembled from profile entities (skills, experiences, education,
certifications) or from the deterministic ``JobMatch`` result, and every claim is
recorded as a ``fact_sources`` reference so it can be traced back to the profile.

Job descriptions remain untrusted input: they may shape *which* questions are
asked and which profile facts are highlighted, but they can never inject
candidate facts.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from uuid import UUID

from backend.core.exceptions import NotFoundError, ValidationError
from backend.models.application import (
    AnswerStatus,
    Application,
    ApplicationAnswer,
    ApplicationDocument,
    ApplicationStatus,
    DocumentType,
    QuestionCategory,
)
from backend.models.candidate import Candidate, CandidateSkill, Certification, Education, Experience
from backend.models.company import Company
from backend.models.job import Job
from backend.models.job_match import JobMatch
from backend.models.resume import Resume, ResumeType
from backend.repositories.application import (
    ApplicationAnswerRepository,
    ApplicationDocumentRepository,
    ApplicationQuestionRepository,
    ApplicationRepository,
)
from backend.repositories.audit import AuditRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.certification import CertificationRepository
from backend.repositories.company import CompanyRepository
from backend.repositories.education import EducationRepository
from backend.repositories.experience import ExperienceRepository
from backend.repositories.job import JobRepository
from backend.repositories.job_match import JobMatchRepository
from backend.repositories.resume import ResumeRepository
from backend.repositories.skill import SkillRepository

GENERATION_RULES_VERSION = "1.0.0"

_CLEARANCE_TERMS = ("clearance", "security clearance", "top secret", "ts/sci", "sv")
_WORK_AUTH_TERMS = (
    "work authorization",
    "legally authorized",
    "right to work",
    "eligible to work",
    "work permit",
    "visa sponsorship",
    "citizenship",
)

_KNOWN_SKILLS = {
    "python",
    "java",
    "go",
    "golang",
    "rust",
    "typescript",
    "javascript",
    "react",
    "angular",
    "fastapi",
    "flask",
    "django",
    "kubernetes",
    "docker",
    "aws",
    "azure",
    "gcp",
    "terraform",
    "linux",
    "postgresql",
    "mysql",
    "mongodb",
    "redis",
    "kafka",
    "rabbitmq",
    "graphql",
    "rest",
    "grpc",
    "tensorflow",
    "pytorch",
    "scikit-learn",
    "pandas",
    "numpy",
    "spark",
    "hadoop",
    "airflow",
    "git",
    "jenkins",
    "ci/cd",
    "microservices",
    "mlops",
    "genai",
    "llm",
    "rag",
    "semantic",
    "sql",
    "nosql",
}


class _FactKind(str, Enum):
    CANDIDATE = "candidate"
    SKILL = "skill"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    CERTIFICATION = "certification"
    MATCH = "match"
    JOB = "job"
    CONTACT = "contact"


@dataclass
class FactSource:
    """A single traceable claim reference."""

    kind: _FactKind
    text: str
    ref_id: UUID | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "ref_id": str(self.ref_id) if self.ref_id is not None else None,
            "text": self.text,
        }


@dataclass
class ProfileFacts:
    """Fact corpus derived exclusively from the candidate profile + match."""

    candidate: Candidate | None = None
    skills: list[CandidateSkill] = field(default_factory=list)
    experiences: list[Experience] = field(default_factory=list)
    educations: list[Education] = field(default_factory=list)
    certifications: list[Certification] = field(default_factory=list)
    match: JobMatch | None = None
    job: Job | None = None
    company: Company | None = None

    def entities(self) -> list[FactSource]:
        facts: list[FactSource] = []
        if self.candidate is not None:
            for label in (self.candidate.full_name, self.candidate.headline, self.candidate.current_role):
                if label:
                    facts.append(FactSource(_FactKind.CANDIDATE, label, self.candidate.id))
        for skill in self.skills:
            facts.append(FactSource(_FactKind.SKILL, skill.name, skill.id))
        for exp in self.experiences:
            facts.append(FactSource(_FactKind.EXPERIENCE, exp.title, exp.id))
            facts.append(FactSource(_FactKind.EXPERIENCE, exp.company_name, exp.id))
            for resp in exp.responsibilities:
                facts.append(FactSource(_FactKind.EXPERIENCE, resp, exp.id))
            for ach in exp.achievements:
                facts.append(FactSource(_FactKind.EXPERIENCE, ach, exp.id))
            for tech in exp.technologies:
                facts.append(FactSource(_FactKind.EXPERIENCE, tech, exp.id))
            if exp.domain:
                facts.append(FactSource(_FactKind.EXPERIENCE, exp.domain, exp.id))
        for edu in self.educations:
            facts.append(FactSource(_FactKind.EDUCATION, edu.degree, edu.id))
            facts.append(FactSource(_FactKind.EDUCATION, edu.institution, edu.id))
        for cert in self.certifications:
            facts.append(FactSource(_FactKind.CERTIFICATION, cert.name, cert.id))
        return facts

    def claim_corpus(self) -> set[str]:
        raw = [f.text.strip() for f in self.entities() if f.text.strip()]
        if self.job is not None and self.job.title:
            raw.append(self.job.title)
        if self.company is not None and self.company.name:
            raw.append(self.company.name)
        corpus: set[str] = set()
        for text in raw:
            corpus.add(text.lower())
            corpus.update(t.lower() for t in re.findall(r"[a-zA-Z][a-zA-Z0-9+#./\-]{1,}", text))
        return corpus


class FactGroundingValidator:
    """Structured validation that generated output never invents claims.

    Facts are the candidate-entered profile entities plus the job title and
    company name (both verified inputs to the preparation step). A sentence is
    flagged as unsupported if it contains a capitalized proper-noun-like token
    that (a) is not one of those facts, and (b) is not a stock prose/framing
    word (salutations, transitions, section headers, polite language).

    Plain prose with no such tokens passes as non-claim framing. For the
    deterministic writer every entity is pulled from the corpus by construction
    so nothing is flagged; the guard exists to reject hypothetical LLM output
    that introduces invented companies, names, or qualifications.
    """

    _CAP_TOKEN = re.compile(r"\b[A-Z][a-zA-Z0-9+/#.\-]{2,}\b")
    _SKILL_TOKEN = re.compile(r"\b[a-zA-Z][a-zA-Z0-9\+#.\-]{2,}\b")

    _FRAMING = {
        "dear",
        "hiring",
        "team",
        "sincerely",
        "thank",
        "please",
        "i",
        "my",
        "you",
        "your",
        "yours",
        "the",
        "this",
        "that",
        "these",
        "those",
        "we",
        "our",
        "in",
        "at",
        "as",
        "for",
        "with",
        "on",
        "and",
        "or",
        "but",
        "per",
        "present",
        "skills",
        "experience",
        "education",
        "certifications",
        "screening",
        "answers",
        "based",
        "would",
        "well",
        "aligned",
        "such",
        "including",
        "gained",
        "role",
        "roles",
        "company",
        "companies",
        "note",
        "notes",
        "however",
        "therefore",
        "candidate",
        "q",
        "a",
        "describe",
        "which",
        "what",
        "why",
        "how",
        "explain",
        "confirm",
        "willing",
        "address",
        "missing",
        "requirement",
        "requirements",
        "relevant",
        "most",
        "salary",
        "compensation",
        "expectations",
        "professional",
        "background",
        "ai",
        "llm",
        "bss",
        "oss",
        "cpq",
        "pim",
        "genai",
        "mlops",
        "ci/cd",
        "rest",
        "api",
        "apis",
        "http",
        "https",
        "sql",
        "html",
        "css",
        "pdf",
        "docx",
        "skill",
        "years",
        "yrs",
        "current",
        "currently",
        "jan",
        "feb",
        "mar",
        "apr",
        "may",
        "jun",
        "jul",
        "aug",
        "sep",
        "oct",
        "nov",
        "dec",
        "usd",
        "eur",
        "gbp",
        "inr",
        "cad",
        "aud",
        "cover",
        "letter",
        "tailored",
        "resume",
        "draft",
        "apply",
        "applying",
        "opportunity",
        "discuss",
        "contribute",
        "considered",
        "consideration",
        "interview",
        "thanks",
        "best",
        "regards",
        "manager",
        "engineering",
        "platform",
        "application",
        "applications",
        "introduction",
        "from",
        "re",
        "regarding",
        "follow",
        "followup",
        "interested",
        "interest",
        "remain",
        "understand",
        "tl",
        "dr",
        "mr",
        "mrs",
    }

    def __init__(self, skill_names: set[str] | None = None) -> None:
        self.skill_names = skill_names or _KNOWN_SKILLS

    def validate(self, text: str, facts: ProfileFacts) -> list[str]:
        corpus = facts.claim_corpus()
        unsupported: list[str] = []
        for sentence in self._sentences(text):
            if self._unsupported(sentence, corpus):
                unsupported.append(sentence)
        return unsupported

    def _sentences(self, text: str) -> list[str]:
        parts = re.split(r"(?<=[.!?])\s+", text.replace("\n", " "))
        return [p.strip() for p in parts if p.strip()]

    def _unsupported(self, sentence: str, corpus: set[str]) -> bool:
        for token in self._CAP_TOKEN.findall(sentence):
            token_lower = token.lower()
            if token_lower in corpus:
                continue
            if token_lower in self._FRAMING:
                continue
            if token_lower in self.skill_names:
                continue
            return True
        for token in self._SKILL_TOKEN.findall(sentence):
            token_lower = token.lower()
            if token_lower in self.skill_names and token_lower not in corpus:
                return True
        return False


@dataclass
class GeneratedQuestion:
    category: QuestionCategory
    question_text: str
    status: AnswerStatus
    answer_text: str = ""
    fact_sources: list[FactSource] = field(default_factory=list)
    source_hint: str | None = None


@dataclass
class GeneratedDocument:
    doc_type: DocumentType
    title: str
    content: str
    fact_sources: list[FactSource]


class ApplicationWriter(ABC):
    """Interface for application material writers."""

    @abstractmethod
    async def prepare_content(self, facts: ProfileFacts) -> list[GeneratedQuestion]:
        """Produce screening questions and fact-grounded answers."""

    @abstractmethod
    async def generate_document(
        self, facts: ProfileFacts, doc_type: DocumentType
    ) -> GeneratedDocument:
        """Generate a fact-grounded document of the requested type."""

    @abstractmethod
    async def validate_document(
        self, document: GeneratedDocument, facts: ProfileFacts
    ) -> list[str]:
        """Return unsupported claims found in a generated document."""


class DeterministicApplicationWriter(ApplicationWriter):
    """Templated, fully deterministic writer grounded in profile facts."""

    def __init__(self, validator: FactGroundingValidator | None = None) -> None:
        self.validator = validator or FactGroundingValidator()

    async def prepare_content(self, facts: ProfileFacts) -> list[GeneratedQuestion]:
        questions: list[GeneratedQuestion] = []

        experience_question = self._experience_question(facts)
        if experience_question is not None:
            questions.append(experience_question)

        relevant = await self._relevant_skill_names(facts) if self._has_match(facts) else []
        skill_question = self._skill_question(facts, relevant)
        if skill_question is not None:
            questions.append(skill_question)

        compensation = self._compensation_question(facts)
        if compensation is not None:
            questions.append(compensation)

        work_auth = self._work_auth_question(facts)
        if work_auth is not None:
            questions.append(work_auth)

        clearance = self._clearance_question(facts)
        if clearance is not None:
            questions.append(clearance)

        for skill in facts.match.missing_skills[:2] if facts.match is not None else []:
            questions.append(
                GeneratedQuestion(
                    category=QuestionCategory.TECHNICAL,
                    question_text=f"Please explain how you would address the missing requirement: {skill}.",
                    status=AnswerStatus.REQUIRES_REVIEW,
                    source_hint="missing skill",
                )
            )

        relocation = self._relocation_question(facts)
        if relocation is not None:
            questions.append(relocation)

        questions.append(
            GeneratedQuestion(
                category=QuestionCategory.MOTIVATION,
                question_text=self._motivation_question_text(facts),
                status=AnswerStatus.REQUIRES_REVIEW,
                source_hint="human input",
            )
        )
        return questions

    async def generate_document(
        self, facts: ProfileFacts, doc_type: DocumentType
    ) -> GeneratedDocument:
        if doc_type == DocumentType.COVER_LETTER:
            return self._cover_letter(facts)
        if doc_type == DocumentType.TAILORED_RESUME:
            return self._tailored_resume(facts)
        if doc_type == DocumentType.ANSWERS_SHEET:
            questions = await self.prepare_content(facts)
            return self._answers_sheet(facts, questions)
        raise ValidationError(f"Unsupported document type: {doc_type}")

    async def validate_document(
        self, document: GeneratedDocument, facts: ProfileFacts
    ) -> list[str]:
        if document.doc_type == DocumentType.ANSWERS_SHEET:
            # For the answers sheet only claim-bearing lines are checked; the
            # question stems echo job requirements (untrusted input) and the
            # "(requires manual input)" placeholder is not a claim.
            flagged: list[str] = []
            for line in document.content.splitlines():
                stripped = line.strip()
                if (
                    stripped.startswith("A: ")
                    and "requires manual input" not in stripped
                ):
                    flagged.extend(self.validator.validate(stripped[3:], facts))
            return flagged
        return self.validator.validate(document.content, facts)

    def _jobs_text(self, facts: ProfileFacts) -> str:
        return (facts.job.description or "") if facts.job is not None else ""

    def _has_match(self, facts: ProfileFacts) -> bool:
        return facts.match is not None

    async def _relevant_skill_names(self, facts: ProfileFacts) -> list[str]:
        if facts.match is None:
            return []
        return self._matched_skills_in_profile(facts)

    # ---------------------------------------------------------------- questions

    def _experience_question(self, facts: ProfileFacts) -> GeneratedQuestion | None:
        if not facts.experiences:
            return None
        titles = ", ".join(exp.title for exp in facts.experiences[:3])
        text = "Describe your professional experience relevant to this role."
        return GeneratedQuestion(
            category=QuestionCategory.EXPERIENCE,
            question_text=text,
            status=AnswerStatus.AUTO,
            answer_text=f"My professional background includes {titles}.",
            fact_sources=[
                FactSource(_FactKind.EXPERIENCE, exp.title, exp.id) for exp in facts.experiences[:3]
            ],
            source_hint="profile",
        )

    def _skill_question(
        self, facts: ProfileFacts, relevant: list[str]
    ) -> GeneratedQuestion | None:
        names = sorted({s.name for s in facts.skills})
        if not names:
            return None
        if relevant:
            text = "Which of your skills are most relevant to this role?"
            answer = "I bring relevant skills including " + ", ".join(relevant) + "."
            sources = [
                FactSource(_FactKind.SKILL, s.name, s.id)
                for s in facts.skills
                if s.name in set(relevant)
            ]
        else:
            text = "Describe your core technical and professional skills."
            answer = "My core skills include " + ", ".join(names[:10]) + "."
            sources = [
                FactSource(_FactKind.SKILL, s.name, s.id) for s in facts.skills[:10]
            ]
        return GeneratedQuestion(
            category=QuestionCategory.TECHNICAL,
            question_text=text,
            status=AnswerStatus.AUTO,
            answer_text=answer,
            fact_sources=sources,
            source_hint="profile",
        )

    def _compensation_question(self, facts: ProfileFacts) -> GeneratedQuestion | None:
        candidate = facts.candidate
        if candidate is None or not candidate.expected_compensation_amount:
            return GeneratedQuestion(
                category=QuestionCategory.COMPENSATION,
                question_text="What are your salary or compensation expectations?",
                status=AnswerStatus.REQUIRES_REVIEW,
                source_hint="human input",
            )
        amount = candidate.expected_compensation_amount
        currency = candidate.expected_compensation_currency or "USD"
        text = "What are your salary or compensation expectations?"
        return GeneratedQuestion(
            category=QuestionCategory.COMPENSATION,
            question_text=text,
            status=AnswerStatus.AUTO,
            answer_text=f"My compensation expectation is {amount:g} in {currency}.",
            fact_sources=[
                FactSource(
                    _FactKind.CANDIDATE,
                    f"{amount:g} {currency}",
                    candidate.id,
                )
            ],
            source_hint="profile",
        )

    def _work_auth_question(self, facts: ProfileFacts) -> GeneratedQuestion | None:
        text = self._jobs_text(facts).lower()
        if not any(t in text for t in _WORK_AUTH_TERMS):
            return None
        candidate = facts.candidate
        candidate_pref = (candidate.work_authorization or "").strip() if candidate else ""
        if candidate_pref:
            return GeneratedQuestion(
                category=QuestionCategory.WORK_AUTHORIZATION,
                question_text="Confirm your work authorization status.",
                status=AnswerStatus.AUTO,
                answer_text=f"My work authorization status is {candidate_pref}.",
                fact_sources=[FactSource(_FactKind.CANDIDATE, candidate_pref, candidate.id)] if candidate else [],
                source_hint="profile",
            )
        return GeneratedQuestion(
            category=QuestionCategory.WORK_AUTHORIZATION,
            question_text="Confirm your work authorization status.",
            status=AnswerStatus.REQUIRES_REVIEW,
            source_hint="human input",
        )

    def _clearance_question(self, facts: ProfileFacts) -> GeneratedQuestion | None:
        text = self._jobs_text(facts).lower()
        if not any(t in text for t in _CLEARANCE_TERMS):
            return None
        return GeneratedQuestion(
            category=QuestionCategory.CLEARANCE,
            question_text="Do you hold the security clearance required for this role?",
            status=AnswerStatus.REQUIRES_REVIEW,
            source_hint="job requirement",
        )

    def _relocation_question(self, facts: ProfileFacts) -> GeneratedQuestion | None:
        candidate = facts.candidate
        job = facts.job
        if candidate is None or job is None:
            return None
        current_loc = candidate.current_location
        if isinstance(current_loc, dict):
            current_parts = [str(v) for v in current_loc.values() if v]
            current = " ".join(current_parts).strip().lower()
        else:
            current = (str(current_loc) if current_loc else "").strip().lower()
        job_loc = (job.location or "").strip().lower()
        if current and job_loc and job_loc not in current:
            return GeneratedQuestion(
                category=QuestionCategory.LOCATION,
                question_text=f"Are you willing to work at {job.location}?",
                status=AnswerStatus.REQUIRES_REVIEW,
                source_hint="job location",
            )
        return None

    def _motivation_question_text(self, facts: ProfileFacts) -> str:
        job = facts.job
        company = facts.company.name if facts.company else ""
        if job is not None and company:
            return f"Why are you interested in the {job.title} role at {company}?"
        return "Why are you interested in this role?"

    # --------------------------------------------------------------- documents

    def _cover_letter(self, facts: ProfileFacts) -> GeneratedDocument:
        candidate = facts.candidate
        job = facts.job
        company = facts.company.name if facts.company else "your company"
        sources = facts.entities()
        name = candidate.full_name if candidate and candidate.full_name else "Candidate"
        opener = self._opener(facts, company)
        body = self._cover_body(facts)
        closing = self._cover_closing(facts)
        content = (
            f"Dear Hiring Team,\n\n"
            f"{opener}\n\n{body}\n\n{closing}\n\n"
            f"Sincerely,\n{name}"
        )
        title = f"Cover Letter - {job.title if job else 'Role'}"
        return GeneratedDocument(
            doc_type=DocumentType.COVER_LETTER,
            title=title,
            content=content.strip(),
            fact_sources=sources,
        )

    def _opener(self, facts: ProfileFacts, company: str) -> str:
        candidate = facts.candidate
        job = facts.job
        job_title = job.title if job is not None else "the role"
        lead = (
            (candidate.current_role or candidate.headline or candidate.target_role)
            if candidate
            else None
        )
        lead_part = f", a {lead}" if lead else ""
        years = self._profile_years(facts)
        years_part = f" with {years}+ years of experience" if years is not None else ""
        exp = next((e for e in facts.experiences if e.is_current), None)
        current_part = (
            f" currently {exp.title} at {exp.company_name}" if exp is not None else ""
        )
        return (
            f"I am {name_only(candidate)}{lead_part}{current_part}{years_part} and wish to "
            f"apply for the {job_title} position at {company}."
        )

    def _cover_body(self, facts: ProfileFacts) -> str:
        paragraphs: list[str] = []
        grounded = self._matched_skills_in_profile(facts)
        if grounded:
            paragraphs.append(
                "My profile is well aligned with this role: I bring relevant experience "
                f"across {', '.join(grounded)}."
            )
        highlights = [
            f"In my {exp.title} role at {exp.company_name}, I worked with {', '.join(exp.technologies)}."
            for exp in facts.experiences[:2]
            if exp.technologies
        ]
        paragraphs.extend(highlights)
        if not paragraphs:
            paragraphs.append(
                "My background, skills, and accomplishments are detailed in the attached resume."
            )
        return "\n\n".join(paragraphs)

    def _matched_skills_in_profile(self, facts: ProfileFacts) -> list[str]:
        """Return match skills that are also present in the candidate profile.

        Raw match strengths may echo untrusted job text (e.g. a skill name that
        never appears in the profile). Only profile-grounded skill names are
        allowed into generated narrative so invented claims can never pass
        through the fact-grounded writer.
        """
        if facts.match is None:
            return []
        profile_names = {s.name.lower() for s in facts.skills}
        grounded: list[str] = []
        seen: set[str] = set()
        for skill in list(facts.match.matched_skills) + list(
            facts.match.transferable_skills
        ):
            key = skill.lower()
            if key in profile_names and key not in seen:
                grounded.append(skill)
                seen.add(key)
        return sorted(grounded, key=str.lower)

    def _cover_closing(self, facts: ProfileFacts) -> str:
        job = facts.job
        company = facts.company.name if facts.company else "your company"
        role = job.title if job is not None else "this role"
        return (
            f"I would welcome the opportunity to discuss how my experience could contribute to "
            f"the {role} role at {company}. Thank you for your consideration."
        )

    def _tailored_resume(self, facts: ProfileFacts) -> GeneratedDocument:
        candidate = facts.candidate
        name = candidate.full_name if candidate and candidate.full_name else "Candidate"
        headline = (candidate.headline if candidate and candidate.headline else "").strip()
        summary = (candidate.summary if candidate and candidate.summary else "").strip()
        lines: list[str] = [name]
        if headline:
            lines.append(headline)
        if summary:
            lines.append("")
            lines.append(summary)
        if facts.skills:
            lines.append("")
            lines.append("SKILLS")
            for skill in sorted(facts.skills, key=lambda s: s.name.lower()):
                meta = f"  - {skill.name}"
                if skill.years_experience is not None:
                    meta += f" ({skill.years_experience} yrs)"
                lines.append(meta)
        if facts.experiences:
            lines.append("")
            lines.append("EXPERIENCE")
            for exp in facts.experiences:
                lines.append(f"  {exp.title} | {exp.company_name}")
                period = _date_range(exp.start_date, exp.end_date, exp.is_current)
                if period:
                    lines.append(f"    {period}")
                for ach in exp.achievements:
                    lines.append(f"    - {ach}")
                for resp in exp.responsibilities:
                    lines.append(f"    - {resp}")
        if facts.educations:
            lines.append("")
            lines.append("EDUCATION")
            for edu in facts.educations:
                degree = f"{edu.degree} - {edu.institution}"
                if edu.field_of_study:
                    degree += f", {edu.field_of_study}"
                lines.append(f"  {degree}")
        if facts.certifications:
            lines.append("")
            lines.append("CERTIFICATIONS")
            for cert in facts.certifications:
                lines.append(f"  {cert.name}")
        content = "\n".join(lines)
        job = facts.job
        title = f"Tailored Resume - {job.title if job else 'Role'}"
        return GeneratedDocument(
            doc_type=DocumentType.TAILORED_RESUME,
            title=title,
            content=content.strip(),
            fact_sources=facts.entities(),
        )

    def _answers_sheet(
        self, facts: ProfileFacts, questions: list[GeneratedQuestion]
    ) -> GeneratedDocument:
        job = facts.job
        company = facts.company.name if facts.company else ""
        header = f"Screening Answers - {job.title if job else 'Role'}"
        if company and job is not None:
            header += f" at {company}"
        lines: list[str] = [header, ""]
        sources: list[FactSource] = []
        for question in questions:
            lines.append(f"Q: {question.question_text}")
            if question.status == AnswerStatus.AUTO and question.answer_text:
                lines.append(f"A: {question.answer_text}")
            else:
                lines.append("A: (requires manual input)")
            sources.extend(question.fact_sources)
            lines.append("")
        content = "\n".join(lines).strip()
        return GeneratedDocument(
            doc_type=DocumentType.ANSWERS_SHEET,
            title=header,
            content=content,
            fact_sources=sources,
        )

    def _profile_years(self, facts: ProfileFacts) -> int | None:
        candidate = facts.candidate
        if candidate is not None and candidate.total_experience_years is not None:
            return max(candidate.total_experience_years, 1)
        if not facts.experiences:
            return None
        total = 0.0
        for exp in facts.experiences:
            if exp.start_date is None:
                continue
            end = exp.end_date or date.today()
            years = max((end - exp.start_date).days / 365.25, 0)
            total += years
        return max(round(total), 1)


def name_only(candidate: Candidate | None) -> str:
    if candidate is None or not candidate.full_name:
        return "the candidate"
    first = candidate.full_name.split()[0]
    return first


def _date_range(start: date, end: date | None, is_current: bool) -> str:
    def fmt(value: date) -> str:
        return value.strftime("%b %Y")

    if is_current or end is None:
        return f"{fmt(start)} - Present"
    return f"{fmt(start)} - {fmt(end)}"


def _resume_type_match(resume_type: ResumeType, title: str) -> int:
    """Score resume-type alignment with a job title for deterministic selection."""
    if resume_type == ResumeType.AI_GENAI and "ai" in title:
        return 30
    if resume_type == ResumeType.ENGINEERING_MANAGER and any(
        t in title for t in ("manager", "lead", "engineering")
    ):
        return 30
    if resume_type == ResumeType.TECHNICAL_MANAGER and "technical" in title:
        return 30
    if resume_type == ResumeType.SOLUTION_ARCHITECT and any(
        t in title for t in ("architect", "solution")
    ):
        return 30
    if resume_type == ResumeType.GENERAL:
        return 10
    return 0


class ApplicationPrepService:
    def __init__(
        self,
        candidate_repo: CandidateRepository,
        job_repo: JobRepository,
        company_repo: CompanyRepository,
        resume_repo: ResumeRepository,
        skill_repo: SkillRepository,
        experience_repo: ExperienceRepository,
        education_repo: EducationRepository,
        certification_repo: CertificationRepository,
        match_repo: JobMatchRepository,
        app_repo: ApplicationRepository,
        question_repo: ApplicationQuestionRepository,
        answer_repo: ApplicationAnswerRepository,
        document_repo: ApplicationDocumentRepository,
        audit_repo: AuditRepository,
        writer: ApplicationWriter | None = None,
    ) -> None:
        self.candidate_repo = candidate_repo
        self.job_repo = job_repo
        self.company_repo = company_repo
        self.resume_repo = resume_repo
        self.skill_repo = skill_repo
        self.experience_repo = experience_repo
        self.education_repo = education_repo
        self.certification_repo = certification_repo
        self.match_repo = match_repo
        self.app_repo = app_repo
        self.question_repo = question_repo
        self.answer_repo = answer_repo
        self.document_repo = document_repo
        self.audit_repo = audit_repo
        self.writer = writer or DeterministicApplicationWriter()

    # ------------------------------------------------------------- ownership

    async def _assert_candidate_owned(self, candidate_id: UUID, user_id: UUID) -> Candidate:
        return await self.candidate_repo.get_for_user_or_404(candidate_id, user_id)

    # ---------------------------------------------------------------- prepare

    async def prepare(
        self,
        candidate_id: UUID,
        user_id: UUID,
        job_id: UUID,
        resume_id: UUID | None = None,
    ) -> Application:
        candidate = await self._assert_candidate_owned(candidate_id, user_id)
        job = await self.job_repo.get_for_candidate(job_id, candidate_id)
        if job is None:
            raise NotFoundError("Job not found")
        match = await self.match_repo.get_for_job(candidate_id, job_id)
        if match is None:
            raise ValidationError(
                "Evaluate the job match first (POST /jobs/{job_id}/match) before preparing materials"
            )

        existing = await self.app_repo.get_by_job(job_id, candidate_id)
        if existing is not None and existing.status != ApplicationStatus.WITHDRAWN:
            return existing

        resume = None
        resume_choice: dict[str, object] = {}
        if resume_id is not None:
            resume = await self.resume_repo.get_with_active_version(resume_id)
            if resume is None or resume.candidate_id != candidate_id:
                raise NotFoundError("Resume not found")
        else:
            resumes = await self.resume_repo.list_active(candidate_id)
            selected = await self._select_resume(resumes, job)
            if selected is not None:
                resume = selected
        if resume is not None:
            resume_choice = {
                "resume_id": str(resume.id),
                "resume_name": resume.name,
                "reason": "selected by ResumeSelector",
            }

        match_score = float(match.score) if match.score is not None else None
        application = await self.app_repo.create(
            candidate_id=candidate_id,
            job_id=job_id,
            resume_id=resume.id if resume is not None else None,
            status=ApplicationStatus.DRAFT,
            match_id=match.id,
            match_score=match_score,
        )

        facts = await self._load_facts(candidate, job, match)
        questions = await self.writer.prepare_content(facts)
        for generated in questions:
            question = await self.question_repo.create(
                application_id=application.id,
                category=generated.category,
                question_text=generated.question_text,
                source_hint=generated.source_hint,
            )
            await self.answer_repo.create(
                application_id=application.id,
                question_id=question.id,
                status=generated.status,
                answer_text=generated.answer_text,
                fact_sources=[f.to_dict() for f in generated.fact_sources],
            )

        for doc_type in (
            DocumentType.COVER_LETTER,
            DocumentType.TAILORED_RESUME,
            DocumentType.ANSWERS_SHEET,
        ):
            await self.generate_document(
                candidate_id, user_id, application.id, doc_type, facts=facts
            )

        await self.audit_repo.log(
            "application.prepared",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="application",
            entity_id=application.id,
            metadata={"job_id": str(job_id), "resume_id": resume_choice.get("resume_id")},
        )
        return application

    # -------------------------------------------------------------- documents

    async def generate_document(
        self,
        candidate_id: UUID,
        user_id: UUID,
        application_id: UUID,
        doc_type: DocumentType,
        facts: ProfileFacts | None = None,
    ) -> ApplicationDocument:
        application = await self._get_owned_application(candidate_id, user_id, application_id)
        if facts is None:
            facts = await self._facts_for_application(application)
        document = await self.writer.generate_document(facts, doc_type)
        unsupported = await self.writer.validate_document(document, facts)
        if unsupported:
            raise ValidationError(
                "Generated document contains unsupported claims: " + "; ".join(unsupported)
            )
        version = await self.document_repo.next_version_number(
            application.id, doc_type=doc_type
        )
        stored = await self.document_repo.create(
            application_id=application.id,
            doc_type=doc_type,
            title=document.title,
            version_number=version,
            is_generated=True,
            content=document.content,
            generation_version=GENERATION_RULES_VERSION,
            fact_sources=[f.to_dict() for f in document.fact_sources],
        )
        await self.audit_repo.log(
            "application.document_generated",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="application_document",
            entity_id=stored.id,
            metadata={"doc_type": doc_type.value, "version": version},
        )
        return stored

    async def list_documents(
        self, candidate_id: UUID, user_id: UUID, application_id: UUID
    ) -> list[ApplicationDocument]:
        application = await self._get_owned_application(candidate_id, user_id, application_id)
        return await self.document_repo.list_for_application(application.id)

    async def get_document(
        self,
        candidate_id: UUID,
        user_id: UUID,
        application_id: UUID,
        document_id: UUID,
    ) -> ApplicationDocument:
        application = await self._get_owned_application(candidate_id, user_id, application_id)
        document = await self.document_repo.get_for_application(document_id, application.id)
        if document is None:
            raise NotFoundError("Document not found")
        return document

    # ------------------------------------------------------------- applications

    async def list_applications(
        self, candidate_id: UUID, user_id: UUID, limit: int, offset: int
    ) -> tuple[list[Application], int]:
        await self._assert_candidate_owned(candidate_id, user_id)
        items = await self.app_repo.list_for_candidate(candidate_id, limit=limit, offset=offset)
        all_items = await self.app_repo.list_for_candidate(candidate_id, limit=10000, offset=0)
        return items, len(all_items)

    async def get_application(
        self, candidate_id: UUID, user_id: UUID, application_id: UUID
    ) -> Application:
        return await self._get_owned_application(candidate_id, user_id, application_id)

    async def get_application_detail(
        self, candidate_id: UUID, user_id: UUID, application_id: UUID
    ) -> Application:
        await self._assert_candidate_owned(candidate_id, user_id)
        application = await self.app_repo.get_detailed(application_id, candidate_id)
        if application is None:
            raise NotFoundError("Application not found")
        return application

    async def update_status(
        self,
        candidate_id: UUID,
        user_id: UUID,
        application_id: UUID,
        status: ApplicationStatus,
    ) -> Application:
        application = await self._get_owned_application(candidate_id, user_id, application_id)
        updated = await self.app_repo.update(application, status=status)
        await self.audit_repo.log(
            "application.status_updated",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="application",
            entity_id=application.id,
            metadata={"status": status.value},
        )
        return updated

    async def update_answer(
        self,
        candidate_id: UUID,
        user_id: UUID,
        application_id: UUID,
        question_id: UUID,
        answer_text: str,
    ) -> ApplicationAnswer:
        application = await self._get_owned_application(candidate_id, user_id, application_id)
        question = await self.question_repo.get(question_id)
        if question is None or question.application_id != application.id:
            raise NotFoundError("Question not found")
        answer = await self.answer_repo.get_for_question(question_id)
        if answer is None:
            answer = await self.answer_repo.create(
                application_id=application.id,
                question_id=question.id,
                status=AnswerStatus.MANUAL,
                answer_text=answer_text,
                fact_sources=[{"kind": "candidate", "ref_id": None, "text": "manual input"}],
            )
        else:
            answer = await self.answer_repo.update(
                answer, status=AnswerStatus.MANUAL, answer_text=answer_text
            )
        await self.audit_repo.log(
            "application.answer_updated",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="application_answer",
            entity_id=answer.id,
            metadata={"application_id": str(application.id), "question_id": str(question.id)},
        )
        return answer

    # ------------------------------------------------------------------ helpers

    async def _get_owned_application(
        self, candidate_id: UUID, user_id: UUID, application_id: UUID
    ) -> Application:
        await self._assert_candidate_owned(candidate_id, user_id)
        application = await self.app_repo.get_for_candidate(application_id, candidate_id)
        if application is None:
            raise NotFoundError("Application not found")
        return application

    async def _facts_for_application(self, application: Application) -> ProfileFacts:
        candidate = await self.candidate_repo.get(application.candidate_id)
        job = await self.job_repo.get(application.job_id)
        match = await self.match_repo.get(application.match_id) if application.match_id else None
        company = None
        if job is not None:
            company = await self.company_repo.get(job.company_id)
        return await self._load_facts(candidate, job, match, company=company)

    async def _load_facts(
        self, candidate: Candidate | None, job: Job | None, match: JobMatch | None, *, company: Company | None = None
    ) -> ProfileFacts:
        if candidate is None:
            return ProfileFacts(candidate=None, match=match, job=job, company=company)
        skills = await self.skill_repo.list_for_candidate(candidate.id)
        experiences = await self.experience_repo.list_ordered(candidate.id)
        educations = await self.education_repo.list_ordered(candidate.id)
        certifications = await self.certification_repo.list_ordered(candidate.id)
        if company is None and job is not None:
            company = await self.company_repo.get(job.company_id)
        return ProfileFacts(
            candidate=candidate,
            skills=[s for s in skills if isinstance(s, CandidateSkill)],
            experiences=[e for e in experiences if isinstance(e, Experience)],
            educations=[e for e in educations if isinstance(e, Education)],
            certifications=[c for c in certifications if isinstance(c, Certification)],
            match=match,
            job=job,
            company=company,
        )

    async def _select_resume(self, resumes: list[Resume], job: Job) -> Resume | None:
        if not resumes:
            return None
        active_with_version = [r for r in resumes if r.active_version is not None]
        pool = active_with_version or resumes

        title = job.title.lower()
        score_map: list[tuple[int, Resume]] = []

        def _score(resume: Resume) -> int:
            score = 0
            if resume.active_version is not None:
                score += 40
            if resume.is_default:
                score += 20
            score += _resume_type_match(resume.resume_type, title)
            target = (resume.target_role or "").lower()
            for word in title.replace("-", " ").split():
                if len(word) > 3 and word in target:
                    score += 5
            return score

        for resume in pool:
            score_map.append((_score(resume), resume))
        score_map.sort(key=lambda pair: pair[0], reverse=True)
        return score_map[0][1]
