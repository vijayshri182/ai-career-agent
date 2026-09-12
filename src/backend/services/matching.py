"""Deterministic, explainable job matching engine.

The engine scores a candidate against a job using ten weighted, transparent
components (skills, role alignment, seniority, experience, domain, industry,
leadership, location, work mode, compensation). Every component contributes a
0.0-1.0 score, a list of human-readable reasons, and optional gap notices. The
final 0-100 score is ``sum(weight_i * component_i) / sum(weights) * 100`` and is
fully reproducible for a given input snapshot.

Job descriptions are treated as **untrusted data**. The parser only tokenizes
text into skills, years, salary and location signals; nothing in a description
can alter the scoring rules, weights, thresholds, or any policy. Semantic
matching (``SemanticSkillMatcher``) may only broaden *related skill credit* and
never weakens hard requirements.
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html import unescape
from uuid import UUID

from backend.models.candidate import Candidate, CandidateSkill, Experience
from backend.models.job import Job
from backend.models.job_match import JobMatch, JobMatchStatus
from backend.repositories.candidate import CandidateRepository
from backend.repositories.experience import ExperienceRepository
from backend.repositories.job import JobRepository
from backend.repositories.job_match import JobMatchRepository
from backend.repositories.skill import SkillRepository
from backend.schemas.matching import BatchMatchResult, JobMatchRead, MatchListResponse
from backend.services.normalization import JobNormalizer
from backend.services.skills import (
    SKILLS,
    SemanticSkillMatcher,
    SkillExtractor,
    SynonymSkillMatcher,
    canonical_skill,
)

RULES_VERSION = "3.0.0"

_REQUIREMENT_SECTIONS = ("requirements", "qualifications", "basic qualifications", "must haves")
_PREFERRED_SECTIONS = ("preferred", "nice to have", "bonus", "plus", "good to have")
_SKIP_SECTIONS = (
    "about",
    "about the role",
    "about us",
    "summary",
    "responsibilities",
    "responsibility",
    "what you'll do",
    "what you will do",
    "benefits",
    "what we offer",
    "why us",
    "company description",
    "day to day",
    "what you ll get",
)

_MUSTBIZ = re.compile(r"\b(must have|must-have|required|mandatory|minimum|essential|must be)\b", re.I)
_PREFBIZ = re.compile(r"\b(preferred|nice to have|nice-to-have|a plus|plus|bonus|good to have)\b", re.I)
_REQUIREMENT_LINE_RE = re.compile(
    r"\b(must have|must-have|required|mandatory|minimum|essential|experience with|experience in|"
    r"knowledge of|familiarity with|proficiency in|hands-on|expertise in|strong knowledge|"
    r"solid understanding|familiar with|ability to|you have|you will have|you bring|proven)\b",
    re.I,
)

_YEARS_RE = re.compile(
    r"(\d{1,2})\s*(?:\+|to|-|–)?\s*(?:years?|yrs?)(?:\s*of)?\s*(?:of\s+)?(?:experience|work|exp)?",
    re.I,
)
_YEARS_RANGE_RE = re.compile(
    r"(\d{1,2})\s*(?:-|–|to)\s*(\d{1,2})\s*(?:years?|yrs?)", re.I
)
_SALARY_RE = re.compile(
    r"(?P<cur>[$€£₹])?\s*(?P<lo>[\d][\d.,]*)\s*(?P<loscale>k|lpa|lakh|ctc)?\s*"
    r"(?:-|–|to)\s*(?P<hi>[\d][\d.,]*)\s*(?P<scale>k|lpa|lakh|l|ctc|per annum|annum|annually|"
    r"a year|per year)?",
    re.IGNORECASE,
)
_SINGLE_SALARY_RE = re.compile(
    r"(?P<cur>[$€£₹])?\s*(?P<amt>[\d][\d.,]*)\s*(?P<scale>lpa|lakh|ctc)\b", re.I
)
_MONTH_SCALE_RE = re.compile(r"\bper month\b|\b/month\b|monthly", re.I)

_CLEARANCE_TERMS = ("security clearance", "active clearance", "top secret", "ts/sci", "clearance required")
_WORK_AUTH_TERMS = ("work authorization", "legally authorized", "right to work", "eligible to work", "citizenship", "work permit", "visa sponsorship")

_INDUSTRY_TERMS: dict[str, tuple[str, ...]] = {
    "telecommunications": ("telecom", "5g", "lte", "wireless", "mobile network", "telco"),
    "bss_oss": ("bss", "oss", "billing", "provisioning", "service assurance", "mediation", "charging"),
    "banking_finance": ("banking", "fintech", "payments", "financial services", "trading"),
    "saas_software": ("saas", "software", "cloud platform", "b2b", "enterprise software"),
    "ecommerce_retail": ("e-commerce", "ecommerce", "retail", "marketplace"),
    "healthcare": ("healthcare", "hospital", "health tech", "clinical"),
    "gaming": ("gaming", "game development"),
    "manufacturing": ("manufacturing", "industrial", "iot"),
    "consulting": ("consulting", "services firm"),
}

_SENIORITY_ORDER = ("junior", "mid", "senior", "lead", "executive")


def _seniority_of(term: str | None) -> str:
    if not term:
        return "mid"
    text = term.lower()
    if any(k in text for k in ("executive", "chief", "cto", "cfo", "cio", "cxo")):
        return "executive"
    if any(k in text for k in ("director", "head of", "group manager", "vp")):
        return "lead"
    if any(k in text for k in ("senior", "lead", "staff", "principal", "architect", "manager", "engineering manager")):
        return "senior"
    if any(k in text for k in ("junior", "trainee", "graduate", "entry", "associate")):
        return "junior"
    return "mid"


def _seniority_rank(value: str) -> int:
    return _SENIORITY_ORDER.index(value) if value in _SENIORITY_ORDER else 1


@dataclass
class CandidateSkillProfile:
    name: str
    proficiency: str | None = None
    years_experience: int | None = None
    category: str | None = None
    is_primary: bool = False


@dataclass
class CandidateExperienceProfile:
    domain: str | None = None
    responsibilities: list[str] = field(default_factory=list)
    achievements: list[str] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)
    leadership_responsibilities: list[str] = field(default_factory=list)
    team_size: int | None = None


@dataclass
class CandidateProfile:
    headline: str | None = None
    summary: str | None = None
    current_role: str | None = None
    target_role: str | None = None
    total_experience_years: int | None = None
    seniority: str | None = None
    work_mode_preference: str | None = None
    work_authorization: str | None = None
    expected_compensation_amount: int | None = None
    expected_compensation_currency: str | None = None
    career_preferences: dict[str, object] = field(default_factory=dict)
    current_location: dict[str, object] | None = None
    skills: list[CandidateSkillProfile] = field(default_factory=list)
    experiences: list[CandidateExperienceProfile] = field(default_factory=list)

    @property
    def canonical_skills(self) -> set[str]:
        found: set[str] = set()
        for skill in self.skills:
            canonical = canonical_skill(skill.name)
            if canonical:
                found.add(canonical)
        return found

    @property
    def domain_experience_count(self) -> int:
        count = 0
        for exp in self.experiences:
            domain = (exp.domain or "").lower()
            if any(term in domain for term in ("telecom", "oss", "bss", "billing", "network", "5g", "lte")):
                count += 1
        for skill in self.skills:
            if skill.category and skill.category.lower() in {"telecom", "oss_bss"}:
                count += 1
        return count

    @property
    def has_leadership_evidence(self) -> bool:
        if any(exp.leadership_responsibilities for exp in self.experiences):
            return True
        if any((exp.team_size or 0) > 1 for exp in self.experiences):
            return True
        if any(s.name.lower() in {"people management", "team leadership"} for s in self.skills):
            return True
        return _seniority_rank(_seniority_of(self.seniority or self.current_role)) >= 3


@dataclass
class JobView:
    title: str = ""
    location: str | None = None
    description: str | None = None
    company_name: str | None = None
    min_years: int | None = None
    max_years: int | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    required_skills: set[str] = field(default_factory=set)
    preferred_skills: set[str] = field(default_factory=set)
    work_modes: set[str] = field(default_factory=set)
    requires_clearance: bool = False
    requires_work_auth: bool = False


@dataclass(frozen=True)
class ScoreWeights:
    skills: float = 25.0
    role_alignment: float = 20.0
    seniority: float = 10.0
    years_experience: float = 10.0
    domain: float = 10.0
    industry: float = 5.0
    leadership: float = 5.0
    location: float = 5.0
    work_mode: float = 5.0
    compensation: float = 5.0

    def total(self) -> float:
        return sum(
            (
                self.skills,
                self.role_alignment,
                self.seniority,
                self.years_experience,
                self.domain,
                self.industry,
                self.leadership,
                self.location,
                self.work_mode,
                self.compensation,
            )
        )

    @classmethod
    def from_weights_string(cls, raw: str) -> ScoreWeights:
        defaults = cls()
        values = {name: getattr(defaults, name) for name in cls.__dataclass_fields__}
        for part in raw.split(","):
            if "=" not in part:
                continue
            key, _, value = part.partition("=")
            key = key.strip()
            if key in values and value.strip():
                with contextlib.suppress(ValueError):
                    values[key] = max(0.0, float(value.strip()))
        return cls(**values)


class JobTextParser:
    """Deterministically parses untrusted job text into structured signals."""

    def __init__(self) -> None:
        self._normalizer = JobNormalizer()
        self._extractor = SkillExtractor()

    def parse(self, job: JobView | None = None, *, title: str, location: str | None, description: str | None) -> JobView:
        normalized_title = self._normalizer.normalize_text(title)
        normalized_location = self._normalizer.clean_optional(location)
        normalized_description = self._normalizer.clean_optional(description)
        target = job or JobView()
        target.title = normalized_title
        target.location = normalized_location
        target.description = normalized_description

        full = " ".join(filter(None, (normalized_title, normalized_location, normalized_description)))
        parse_text = self._clean_for_parsing(description)
        target.min_years, target.max_years = self._parse_years(parse_text)
        self._parse_salary(parse_text, target)
        self._parse_skill_sections(parse_text, target)
        target.work_modes = self._parse_work_modes(full)
        target.requires_clearance = any(term in full.lower() for term in _CLEARANCE_TERMS)
        target.requires_work_auth = any(term in full.lower() for term in _WORK_AUTH_TERMS)
        return target

    @staticmethod
    def _clean_for_parsing(text: str | None) -> str:
        if not text:
            return ""
        text = unescape(text).replace("\u00a0", " ")
        return "\n".join(" ".join(line.split()) for line in text.splitlines())

    def _parse_years(self, text: str) -> tuple[int | None, int | None]:
        if not text:
            return None, None
        range_match = _YEARS_RANGE_RE.search(text)
        if range_match:
            low = int(range_match.group(1))
            high = int(range_match.group(2))
            return low, high if high > low else None
        match = _YEARS_RE.search(text)
        if match:
            value = int(match.group(1))
            return value, None
        return None, None

    def _parse_salary(self, text: str, target: JobView) -> None:
        if not text:
            return
        currency = None
        for match in _SALARY_RE.finditer(text):
            low = match.group("lo")
            high = match.group("hi")
            scale = (match.group("scale") or "").lower()
            loscale = (match.group("loscale") or "").lower()
            cur = match.group("cur")
            if low is None or high is None:
                continue
            lo_raw = self._to_number(low)
            if not cur and not scale and not loscale and lo_raw < 10_000:
                continue
            lo = lo_raw * self._salary_scale(loscale or scale)
            hi = self._to_number(high) * self._salary_scale(scale or loscale)
            currency = currency or self._currency_for(match.group("cur"), scale or loscale)
            if lo > 0:
                target.salary_min = min(target.salary_min or lo, lo)
                target.salary_max = max(target.salary_max or hi, hi)
                currency = currency or self._currency_for(match.group("cur"), scale or loscale)
        single = _SINGLE_SALARY_RE.search(text)
        if single and target.salary_max is None:
            amt = self._to_number(single.group("amt"))
            scale = (single.group("scale") or "").lower()
            annual = amt * self._salary_scale(scale)
            target.salary_min = annual
            target.salary_max = annual
            currency = currency or self._currency_for(None, scale)
        target.salary_currency = currency

    @staticmethod
    def _to_number(value: str) -> float:
        return float(value.replace(",", ""))

    @staticmethod
    def _salary_scale(scale: str) -> float:
        if scale in {"k"}:
            return 1_000.0
        if scale in {"lpa", "lakh", "l", "ctc"}:
            return 100_000.0
        return 1.0

    @staticmethod
    def _currency_for(symbol: str | None, scale: str) -> str | None:
        if symbol == "$":
            return "USD"
        if symbol == "€":
            return "EUR"
        if symbol == "£":
            return "GBP"
        if symbol == "₹" or scale in {"lpa", "lakh", "ctc"}:
            return "INR"
        return None

    def _parse_skill_sections(self, text: str, target: JobView) -> None:
        if not text:
            return
        current_section: str | None = None
        must_lines: list[str] = []
        prefer_lines: list[str] = []
        for line in text.splitlines():
            stripped = line.strip().strip(":")
            if not stripped:
                continue
            lowered = stripped.lower()
            is_break = self._is_section_header(lowered)
            if len(stripped) < 60 and is_break:
                current_section = lowered
                continue
            if not is_break and lowered.startswith(("responsibility", "responsibilities", "what you ")):
                current_section = "responsibility"
                continue
            if current_section is None:
                continue
            if any(key in current_section for key in _SKIP_SECTIONS):
                continue
            if any(key in current_section for key in _PREFERRED_SECTIONS):
                prefer_lines.append(stripped)
            elif any(key in current_section for key in _REQUIREMENT_SECTIONS):
                if _PREFBIZ.search(stripped):
                    prefer_lines.append(stripped)
                elif _REQUIREMENT_LINE_RE.search(stripped) or _MUSTBIZ.search(stripped):
                    must_lines.append(stripped)
        if not must_lines and not prefer_lines:
            required = self._extractor.extract(text)
            target.required_skills = {s for s in required if _MUSTBIZ.search(text)}
            target.preferred_skills = required - target.required_skills
            return
        target.required_skills = self._extract_skills_from_lines(must_lines)
        target.preferred_skills = self._extract_skills_from_lines(prefer_lines)

    @staticmethod
    def _is_section_header(line: str) -> bool:
        keys = _REQUIREMENT_SECTIONS + _PREFERRED_SECTIONS + (
            "about the role", "about us", "what you'll do", "responsibility", "responsibilities",
            "key responsibilities", "job summary", "job description", "the role",
            "responsibilities and duties", "the opportunity",
        )
        heading = line.strip(":").strip()
        if len(heading.split()) > 4:
            return False
        return any(key in heading for key in keys)

    def _extract_skills_from_lines(self, lines: list[str]) -> set[str]:
        skills: set[str] = set()
        for line in lines:
            skills |= self._extractor.extract(line)
        return skills

    @staticmethod
    def _parse_work_modes(text: str) -> set[str]:
        modes: set[str] = set()
        lowered = text.lower()
        if re.search(r"\bremote\b", lowered):
            modes.add("remote")
        if re.search(r"\bhybrid\b", lowered):
            modes.add("hybrid")
        if re.search(r"\bon-?site\b|\bin[- ]office\b", lowered):
            modes.add("onsite")
        return modes


@dataclass
class MatchOutput:
    score: float = 0.0
    confidence: float = 0.0
    is_match: bool = False
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    transferable_skills: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    recommendation_reasons: list[str] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)
    breakdown: dict[str, object] = field(default_factory=dict)


@dataclass
class _Component:
    key: str
    weight: float
    score: float
    reasons: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    blocker_gaps: list[str] = field(default_factory=list)


class JobMatchScorer:
    """Deterministic, explainable scorer. Stateless and reproducible."""

    def __init__(
        self,
        *,
        weights: ScoreWeights | None = None,
        threshold: float = 70.0,
        matcher: SemanticSkillMatcher | None = None,
        rules_version: str = RULES_VERSION,
    ) -> None:
        self.weights = weights or ScoreWeights()
        self.threshold = threshold
        self.matcher = matcher or SynonymSkillMatcher()
        self.rules_version = rules_version

    def score(self, candidate: CandidateProfile, job: JobView) -> MatchOutput:
        components = self._evaluate(candidate, job)
        total_weight = self.weights.total()
        weighted_sum = sum(c.score * c.weight for c in components)
        score = (weighted_sum / total_weight) * 100.0 if total_weight > 0 else 0.0
        score = round(score, 1)

        blockers: list[str] = []
        for comp in components:
            blockers.extend(comp.blocker_gaps)
        if job.requires_clearance:
            blockers.append("Security clearance required")
        if job.requires_work_auth:
            blockers.append("Work authorization required")

        gaps: list[str] = []
        for comp in components:
            for gap in comp.gaps:
                if gap not in gaps:
                    gaps.append(gap)
        for blocker in blockers:
            if blocker not in gaps:
                gaps.append(blocker)

        blockers = list(dict.fromkeys(blockers))

        strengths = [reason for comp in components for reason in comp.reasons]
        matched_skills = self._matched_skill_labels(candidate, job)
        missing_skills = self._missing_skill_labels(candidate, job)
        transferable = self._transferable_skill_labels(candidate, job)

        is_match = score >= self.threshold and not blockers
        recommendation_reasons = self._recommendations(components, strengths, score, blockers)
        rejection_reasons = self._rejections(components, blockers, score)
        confidence = self._confidence(candidate, job)

        breakdown = {
            "rules_version": self.rules_version,
            "threshold": self.threshold,
            "score": score,
            "confidence": confidence,
            "is_match": is_match,
            "weights": {
                c.key: {"weight": c.weight, "component_score": c.score, "points": round(c.score * c.weight, 2)}
                for c in components
            },
            "components": [self._component_dict(c) for c in components],
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "transferable_skills": transferable,
            "blockers": blockers,
        }

        return MatchOutput(
            score=score,
            confidence=confidence,
            is_match=is_match,
            matched_skills=matched_skills,
            missing_skills=missing_skills,
            transferable_skills=transferable,
            strengths=strengths,
            gaps=gaps,
            blockers=blockers,
            recommendation_reasons=recommendation_reasons,
            rejection_reasons=rejection_reasons,
            breakdown=breakdown,
        )

    # -- component evaluation ------------------------------------------------

    def _evaluate(self, candidate: CandidateProfile, job: JobView) -> list[_Component]:
        return [
            self._skills_component(candidate, job),
            self._role_component(candidate, job),
            self._seniority_component(candidate, job),
            self._experience_component(candidate, job),
            self._domain_component(candidate, job),
            self._industry_component(candidate, job),
            self._leadership_component(candidate, job),
            self._location_component(candidate, job),
            self._work_mode_component(candidate, job),
            self._compensation_component(candidate, job),
        ]

    def _skills_component(self, candidate: CandidateProfile, job: JobView) -> _Component:
        required = job.required_skills
        candidate_skills = candidate.canonical_skills
        matched: list[str] = []
        missing: list[str] = []
        transferable: list[str] = []
        credits: list[tuple[str, float]] = []

        pool = sorted(required) if required else sorted(job.preferred_skills)
        if not pool:
            return _Component("skills", self.weights.skills, 1.0, ["No explicit skill requirements listed"])

        for skill_key in pool:
            if skill_key in candidate_skills:
                matched.append(skill_key)
                credits.append((skill_key, 1.0))
                continue
            related = self.matcher.related_skills(skill_key)
            if any(rel in candidate_skills for rel in related):
                transferable.append(skill_key)
                credits.append((skill_key, 0.5))
                continue
            missing.append(skill_key)
            credits.append((skill_key, 0.0))

        score = sum(credit for _, credit in credits) / len(credits) if credits else 1.0
        reasons: list[str] = []
        if matched:
            reasons.append(f"Matched required skill(s): {', '.join(SKILLS.get(k, k) for k in sorted(set(matched)))}")
        if transferable and not matched and not required:
            reasons.append(
                f"Related skill(s) present: {', '.join(SKILLS.get(k, k) for k in sorted(transferable))}"
            )
        gaps_list = [f"Missing required skill: {SKILLS.get(k, k)}" for k in missing]
        return _Component(
            "skills", self.weights.skills, score, reasons, gaps_list, list(gaps_list)
        )

    def _role_component(self, candidate: CandidateProfile, job: JobView) -> _Component:
        target_tokens = self._tokens(f"{candidate.target_role or ''} {candidate.current_role or ''}")
        title_tokens = self._tokens(job.title)
        if not target_tokens or not title_tokens:
            return _Component("role_alignment", self.weights.role_alignment, 0.7, ["Insufficient role context"])
        coverage = len(target_tokens & title_tokens) / len(title_tokens)
        has_direct = any(tok in title_tokens for tok in target_tokens)
        score = min(1.0, 0.25 + 0.45 * coverage + 0.30 * (1.0 if has_direct else 0.0))
        reasons = []
        direct = sorted(target_tokens & title_tokens)
        if direct:
            reasons.append(f"Role aligns with target/current role keywords: {', '.join(direct)}")
        else:
            reasons.append("Title does not visibly overlap target role keywords")
        return _Component("role_alignment", self.weights.role_alignment, score, reasons)

    def _seniority_component(self, candidate: CandidateProfile, job: JobView) -> _Component:
        job_level = _seniority_of(job.title)
        candidate_level = _seniority_of(candidate.seniority or candidate.current_role)
        job_rank = _seniority_rank(job_level)
        cand_rank = _seniority_rank(candidate_level)
        reasons = [f"Job seniority '{job_level}' vs candidate seniority '{candidate_level}'"]
        if job_rank == cand_rank:
            return _Component("seniority", self.weights.seniority, 1.0, reasons)
        if job_rank - cand_rank == 1:
            return _Component("seniority", self.weights.seniority, 0.75, reasons)
        if job_rank - cand_rank >= 2:
            return _Component(
                "seniority",
                self.weights.seniority,
                0.4,
                reasons,
                [f"Role is senior to current profile ({job_level})"],
            )
        return _Component(
            "seniority",
            self.weights.seniority,
            0.6,
            reasons,
            [f"Role may be below candidate seniority ({candidate_level})"],
        )

    def _experience_component(self, candidate: CandidateProfile, job: JobView) -> _Component:
        candidate_years = candidate.total_experience_years
        if job.min_years is None:
            return _Component("years_experience", self.weights.years_experience, 1.0, ["No explicit experience requirement"])
        reasons = [f"Job asks for {job.min_years}+ years of experience"]
        if candidate_years is None:
            return _Component(
                "years_experience",
                self.weights.years_experience,
                0.6,
                reasons,
                ["Candidate experience years not on profile"],
            )
        if candidate_years >= job.min_years:
            return _Component(
                "years_experience",
                self.weights.years_experience,
                1.0,
                [f"Candidate has {candidate_years} years (meets/exceeds requirement)"],
            )
        if candidate_years >= job.min_years * 0.6:
            return _Component(
                "years_experience",
                self.weights.years_experience,
                0.6,
                [f"Candidate has {candidate_years} years (approaching requirement)"],
                [f"Short of the {job.min_years} years typically required"],
            )
        return _Component(
            "years_experience",
            self.weights.years_experience,
            0.25,
            [f"Candidate has {candidate_years} years"],
            [f"Requires {job.min_years} years (hard gap)"],
            [f"Requires {job.min_years} years (hard gap)"],
        )

    def _domain_component(self, candidate: CandidateProfile, job: JobView) -> _Component:
        full = f"{job.title} {job.location or ''} {job.description or ''}".lower()
        domain_terms = ("telecom", "5g", "4g", "lte", "volt", "ims", "core network", "network function", "bss", "oss", "billing", "provisioning", "charging", "mediation", "service assurance")
        job_has_domain = any(term in full for term in domain_terms)
        candidate_domain = min(float(candidate.domain_experience_count), 2.0)
        if not job_has_domain:
            return _Component("domain", self.weights.domain, 0.75, ["No telecom/BSS/OSS-specific requirement detected"])
        if candidate_domain >= 1:
            return _Component(
                "domain",
                self.weights.domain,
                1.0,
                [f"Candidate has telecom/BSS/OSS domain experience (signal count {candidate.domain_experience_count})"],
            )
        return _Component(
            "domain",
            self.weights.domain,
            0.4,
            ["Job is in telecom/BSS/OSS domain"],
            ["No explicit telecom/BSS/OSS domain experience on profile"],
        )

    @staticmethod
    def _list_preference(preferences: dict[str, object], key: str) -> list[str]:
        raw = preferences.get(key, [])
        if not isinstance(raw, list):
            return []
        return [str(item).lower() for item in raw if item]

    def _industry_component(self, candidate: CandidateProfile, job: JobView) -> _Component:
        preferences = candidate.career_preferences or {}
        target_industries = self._list_preference(preferences, "target_industries")
        excluded = self._list_preference(preferences, "exclude_industries")
        full = f"{job.title} {job.location or ''} {job.description or ''}".lower()
        job_industries: list[str] = []
        for industry, terms in _INDUSTRY_TERMS.items():
            if any(term in full for term in terms):
                job_industries.append(industry)
        if not job_industries:
            return _Component("industry", self.weights.industry, 0.7, ["Industry not clearly identified"])
        if any(ind in target_industries for ind in job_industries):
            return _Component("industry", self.weights.industry, 1.0, [f"Industry {', '.join(job_industries)} matches preference"])
        if any(ind in excluded for ind in job_industries):
            return _Component(
                "industry",
                self.weights.industry,
                0.0,
                [f"Industry {', '.join(job_industries)} is on the exclusion list"],
                [f"Job is in excluded industry ({', '.join(job_industries)})"],
            )
        return _Component("industry", self.weights.industry, 0.6, [f"Industry is {', '.join(job_industries)}"])

    def _leadership_component(self, candidate: CandidateProfile, job: JobView) -> _Component:
        full = f"{job.title} {job.description or ''}".lower()
        job_requires = any(
            term in full
            for term in ("lead", "leading", "manage a team", "people management", "mentor", "team lead", "manager", "people leadership")
        )
        candidate_has = candidate.has_leadership_evidence
        if not job_requires:
            return _Component("leadership", self.weights.leadership, 1.0, ["No leadership requirement stated"])
        if candidate_has:
            return _Component("leadership", self.weights.leadership, 1.0, ["Leadership experience evidenced on profile"])
        return _Component(
            "leadership",
            self.weights.leadership,
            0.3,
            ["Role expects leadership responsibilities"],
            ["No explicit leadership/team-management evidence on profile"],
        )

    def _location_component(self, candidate: CandidateProfile, job: JobView) -> _Component:
        preferences = candidate.career_preferences or {}
        preferred_locations = self._list_preference(preferences, "locations")
        excluded_locations = self._list_preference(preferences, "exclude_locations")
        job_location = (job.location or "").lower()
        if "remote" in job.work_modes:
            if candidate.work_mode_preference == "onsite":
                return _Component("location", self.weights.location, 0.5, ["Remote role", "Candidate prefers on-site work"])
            return _Component("location", self.weights.location, 1.0, ["Remote role (location-agnostic)"])
        if not job_location:
            return _Component("location", self.weights.location, 0.8, ["Job location not specified; not penalized"])

        candidate_city = str((candidate.current_location or {}).get("city") or "").lower()
        candidate_country = str((candidate.current_location or {}).get("country") or "").lower()
        city_match = candidate_city and candidate_city in job_location
        country_match = candidate_country and candidate_country in job_location
        if city_match:
            return _Component("location", self.weights.location, 1.0, [f"Job city '{job_location}' matches candidate city"])
        if country_match:
            return _Component("location", self.weights.location, 0.7, [f"Job location '{job_location}' is in candidate's country"])
        if preferred_locations and any(loc in job_location for loc in preferred_locations):
            return _Component("location", self.weights.location, 1.0, ["Job location matches a preferred location"])
        if excluded_locations and any(loc in job_location for loc in excluded_locations):
            return _Component(
                "location",
                self.weights.location,
                0.0,
                [f"Job location '{job_location}' is excluded"],
                [f"Job is in an excluded location ({job_location})"],
            )
        return _Component("location", self.weights.location, 0.5, [f"Job location '{job_location}' does not match current location"])

    def _work_mode_component(self, candidate: CandidateProfile, job: JobView) -> _Component:
        preference = (candidate.work_mode_preference or "").lower()
        if not job.work_modes:
            return _Component("work_mode", self.weights.work_mode, 0.8, ["Work mode not stated"])
        if preference in job.work_modes:
            return _Component("work_mode", self.weights.work_mode, 1.0, [f"Work mode '{preference}' matches requirement"])
        return _Component(
            "work_mode",
            self.weights.work_mode,
            0.3,
            [f"Role is {', '.join(sorted(job.work_modes))}"],
            [f"Candidate prefers '{preference or 'unspecified'}' but role is {', '.join(sorted(job.work_modes))}"],
        )

    def _compensation_component(self, candidate: CandidateProfile, job: JobView) -> _Component:
        expected = candidate.expected_compensation_amount
        if job.salary_min is None or job.salary_max is None:
            return _Component("compensation", self.weights.compensation, 0.8, ["Compensation not disclosed"])
        if expected is None:
            return _Component("compensation", self.weights.compensation, 0.7, ["Candidate compensation expectation not set"])
        range_mid = (job.salary_min + job.salary_max) / 2.0
        if range_mid <= 0:
            return _Component("compensation", self.weights.compensation, 0.8, ["Compensation range unclear"])
        ratio = expected / range_mid
        if 0.6 <= ratio <= 1.4:
            return _Component("compensation", self.weights.compensation, 1.0, [f"Compensation range fits expectation (~{ratio:.0%})"])
        if ratio > 1.4:
            return _Component("compensation", self.weights.compensation, 0.5, [f"Expected compensation is above disclosed range ({range_mid:,.0f})"])
        return _Component(
            "compensation",
            self.weights.compensation,
            0.3,
            [f"Disclosed compensation below expectation ({range_mid:,.0f})"],
            [f"Disclosed compensation ({range_mid:,.0f}) below expected range"],
            [f"Disclosed compensation ({range_mid:,.0f}) below expected range"],
        )

    # -- helpers ---------------------------------------------------------------

    def _matched_skill_labels(self, candidate: CandidateProfile, job: JobView) -> list[str]:
        candidate_skills = candidate.canonical_skills
        pool = job.required_skills or job.preferred_skills
        matched = {k for k in pool if k in candidate_skills}
        return sorted(SKILLS.get(k, k) for k in matched)

    def _missing_skill_labels(self, candidate: CandidateProfile, job: JobView) -> list[str]:
        candidate_skills = candidate.canonical_skills
        return sorted(SKILLS.get(k, k) for k in job.required_skills if k not in candidate_skills)

    def _transferable_skill_labels(self, candidate: CandidateProfile, job: JobView) -> list[str]:
        candidate_skills = candidate.canonical_skills
        found: set[str] = set()
        for skill_key in job.required_skills:
            if skill_key in candidate_skills:
                continue
            if any(rel in candidate_skills for rel in self.matcher.related_skills(skill_key)):
                found.add(skill_key)
        return sorted(SKILLS.get(k, k) for k in found)

    @staticmethod
    def _tokens(text: str) -> set[str]:
        if not text:
            return set()
        tokens = {re.sub(r"[^a-z]", "", tok) for tok in re.findall(r"[A-Za-z][A-Za-z0-9+#-]*", text.lower())}
        stopwords = {"the", "and", "for", "with", "role", "job", "senior", "of", "in", "to"}
        return {t for t in tokens if len(t) > 1 and t not in stopwords}

    def _recommendations(self, components: list[_Component], strengths: list[str], score: float, blockers: list[str]) -> list[str]:
        if blockers:
            return []
        reasons = [r for c in components for r in c.reasons if "not" not in r.lower()]
        result = [f"Overall match {score:.0f}/100"]
        result.extend(reasons[:5])
        return result

    def _rejections(self, components: list[_Component], blockers: list[str], score: float) -> list[str]:
        reasons: list[str] = []
        if blockers:
            reasons.extend(blockers[:4])
        if score < self.threshold:
            reasons.append(f"Score {score:.0f} is below the {self.threshold:.0f} match threshold")
        return reasons

    def _confidence(self, candidate: CandidateProfile, job: JobView) -> float:
        base = 0.55
        if job.description:
            base += 0.10
        if job.location:
            base += 0.05
        if job.required_skills or job.preferred_skills:
            base += 0.05
        if job.salary_min is not None:
            base += 0.05
        if candidate.skills:
            base += 0.10
        if candidate.experiences:
            base += 0.05
        if candidate.target_role:
            base += 0.05
        return round(min(base, 1.0), 2)

    @staticmethod
    def _component_dict(component: _Component) -> dict[str, object]:
        return {
            "key": component.key,
            "weight": component.weight,
            "score": round(component.score, 3),
            "points": round(component.score * component.weight, 2),
            "reasons": component.reasons,
            "gaps": component.gaps,
        }


class JobMatchingService:
    """Persistence-facing matching service.

    Evaluates a candidate against its jobs using the deterministic scorer,
    upserts the result (idempotent per candidate+job), and serves queries.
    """

    def __init__(
        self,
        *,
        candidate_repo: CandidateRepository,
        job_repo: JobRepository,
        match_repo: JobMatchRepository,
        skill_repo: SkillRepository,
        experience_repo: ExperienceRepository,
        scorer: JobMatchScorer,
        parser: JobTextParser | None = None,
    ) -> None:
        self._candidate_repo = candidate_repo
        self._job_repo = job_repo
        self._match_repo = match_repo
        self._skill_repo = skill_repo
        self._experience_repo = experience_repo
        self._scorer = scorer
        self._parser = parser or JobTextParser()

    async def evaluate(self, candidate_id: UUID, user_id: UUID, job_id: UUID) -> JobMatchRead:
        candidate = await self._candidate_repo.get_for_user_or_404(candidate_id, user_id)
        job = await self._job_repo.get_for_candidate(job_id, candidate_id)
        if job is None:
            from backend.core.exceptions import NotFoundError

            raise NotFoundError("Job not found")
        return await self._evaluate_and_persist(candidate, job)

    async def batch_evaluate(
        self, candidate_id: UUID, user_id: UUID, *, limit: int = 50, recompute: bool = False
    ) -> BatchMatchResult:
        candidate = await self._candidate_repo.get_for_user_or_404(candidate_id, user_id)
        jobs = await self._job_repo.list_for_candidate(candidate_id, limit=limit)
        evaluated = 0
        updated = 0
        errors = 0
        matched_count = 0
        rejected_count = 0
        error_metadata: dict[str, str] = {}
        for job in jobs:
            existing = await self._match_repo.get_for_job(candidate_id, job.id)
            if existing is not None and not recompute:
                updated += 1
                if existing.is_match:
                    matched_count += 1
                else:
                    rejected_count += 1
                continue
            try:
                result = await self._evaluate_and_persist(candidate, job)
                updated += 1
                evaluated += 1
                if result.is_match:
                    matched_count += 1
                else:
                    rejected_count += 1
            except Exception as exc:  # noqa: BLE001
                errors += 1
                error_metadata[str(job.id)] = f"{type(exc).__name__}: {exc}"
        return BatchMatchResult(
            candidate_id=candidate_id,
            evaluated=evaluated,
            updated=updated,
            errors=errors,
            matched=matched_count,
            rejected=rejected_count,
            error_metadata=error_metadata,
        )

    async def score_for_orchestrator(self, candidate_id: UUID, job_id: UUID) -> JobMatch | None:
        """Non-API evaluation used by the 24x7 orchestrator (persists result)."""
        candidate = await self._candidate_repo.get(candidate_id)
        if candidate is None:
            return None
        job = await self._job_repo.get(job_id)
        if job is None:
            return None
        await self._evaluate_and_persist(candidate, job)
        return await self._match_repo.get_for_job(candidate_id, job_id)

    async def get_for_job(self, candidate_id: UUID, user_id: UUID, job_id: UUID) -> JobMatchRead:
        from backend.core.exceptions import NotFoundError

        await self._candidate_repo.get_for_user_or_404(candidate_id, user_id)
        match = await self._match_repo.get_for_job(candidate_id, job_id)
        if match is None:
            raise NotFoundError("Job has not been evaluated yet")
        return JobMatchRead.model_validate(match)

    async def list(
        self,
        candidate_id: UUID,
        user_id: UUID,
        *,
        is_match: bool | None = None,
        status: JobMatchStatus | None = None,
        min_score: float | None = None,
        sort: str = "score",
        limit: int = 50,
        offset: int = 0,
    ) -> MatchListResponse:
        await self._candidate_repo.get_for_user_or_404(candidate_id, user_id)
        items = await self._match_repo.list_for_candidate(
            candidate_id,
            is_match=is_match,
            status=status,
            min_score=min_score,
            sort=sort,
            limit=limit,
            offset=offset,
        )
        total = await self._match_repo.count_for_candidate(
            candidate_id, is_match=is_match, status=status, min_score=min_score
        )
        return MatchListResponse(
            items=[JobMatchRead.model_validate(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def _evaluate_and_persist(self, candidate: Candidate, job: Job) -> JobMatchRead:
        profile = await self._load_candidate_profile(candidate)
        job_view = self._parser.parse(
            title=job.title, location=job.location, description=job.description
        )
        output = self._scorer.score(profile, job_view)
        now = datetime.now(UTC)
        result = await self._match_repo.upsert(
            candidate.id,
            job.id,
            status=JobMatchStatus.MATCHED if output.is_match else JobMatchStatus.REJECTED,
            score=output.score,
            confidence=output.confidence,
            is_match=output.is_match,
            matched_skills=output.matched_skills,
            missing_skills=output.missing_skills,
            transferable_skills=output.transferable_skills,
            strengths=output.strengths,
            gaps=output.gaps,
            blockers=output.blockers,
            recommendation_reasons=output.recommendation_reasons,
            rejection_reasons=output.rejection_reasons,
            score_breakdown=output.breakdown,
            rules_version=self._scorer.rules_version,
            evaluated_at=now,
        )
        return JobMatchRead.model_validate(result)

    @staticmethod
    def _enum_value(value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        raw = getattr(value, "value", value)
        return str(raw) if raw is not None else None

    async def _load_candidate_profile(self, candidate: Candidate) -> CandidateProfile:
        skills = await self._skill_repo.list_for_candidate(candidate.id)
        experiences = await self._experience_repo.list_ordered(candidate.id)
        skill_profiles = [
            CandidateSkillProfile(
                name=skill.name,
                proficiency=self._enum_value(skill.proficiency),
                years_experience=skill.years_experience,
                category=self._enum_value(skill.category),
                is_primary=skill.is_primary,
            )
            for skill in skills
            if isinstance(skill, CandidateSkill)
        ]
        experience_profiles = [
            CandidateExperienceProfile(
                domain=exp.domain,
                responsibilities=list(exp.responsibilities or []),
                achievements=list(exp.achievements or []),
                technologies=list(exp.technologies or []),
                leadership_responsibilities=list(exp.leadership_responsibilities or []),
                team_size=exp.team_size,
            )
            for exp in experiences
            if isinstance(exp, Experience)
        ]
        return CandidateProfile(
            headline=candidate.headline,
            summary=candidate.summary,
            current_role=candidate.current_role,
            target_role=candidate.target_role,
            total_experience_years=candidate.total_experience_years,
            seniority=candidate.seniority,
            work_mode_preference=self._enum_value(candidate.work_mode_preference),
            work_authorization=candidate.work_authorization,
            expected_compensation_amount=candidate.expected_compensation_amount,
            expected_compensation_currency=candidate.expected_compensation_currency,
            career_preferences=dict(candidate.career_preferences or {}),
            current_location=candidate.current_location,
            skills=skill_profiles,
            experiences=experience_profiles,
        )
