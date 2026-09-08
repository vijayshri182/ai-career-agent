"""Profile completeness calculation."""

from typing import cast

from backend.core.config import Settings
from backend.models.candidate import (
    Candidate,
    CandidateSkill,
    Certification,
    Education,
    Experience,
)
from backend.models.resume import Resume


class ProfileCompletenessService:
    """Calculate weighted profile completeness."""

    DEFAULT_WEIGHTS = {
        "basic": 15,
        "summary": 10,
        "experience": 20,
        "skills": 15,
        "education": 10,
        "certifications": 5,
        "preferences": 15,
        "resumes": 10,
    }

    def __init__(self, settings: Settings | None = None) -> None:
        self.weights = dict(self.DEFAULT_WEIGHTS)
        if settings and settings.profile_completeness_weights:
            custom_weights: dict[str, int] = {}
            for part in settings.profile_completeness_weights.split(","):
                key, value = part.strip().split("=")
                custom_weights[key.strip()] = int(value.strip())
            self.weights = custom_weights
        self.maximum = sum(self.weights.values())

    def calculate(
        self,
        candidate: Candidate,
        skills: list[CandidateSkill],
        experiences: list[Experience],
        educations: list[Education],
        certifications: list[Certification],
        resumes: list[Resume],
    ) -> dict[str, object]:
        items: list[dict[str, object]] = []

        def weight(key: str) -> int:
            return self.weights.get(key, 0)

        basic_score = self._basic_score(candidate, weight("basic"))
        items.append({"name": "basic", "present": basic_score == weight("basic"), "weight": weight("basic"), "score": basic_score})

        summary_score = weight("summary") if candidate.summary else 0
        items.append({"name": "summary", "present": bool(candidate.summary), "weight": weight("summary"), "score": summary_score})

        exp_score = weight("experience") if experiences else 0
        items.append({"name": "experience", "present": bool(experiences), "weight": weight("experience"), "score": exp_score})

        skills_score = weight("skills") if skills else 0
        items.append({"name": "skills", "present": bool(skills), "weight": weight("skills"), "score": skills_score})

        edu_score = weight("education") if educations else 0
        items.append({"name": "education", "present": bool(educations), "weight": weight("education"), "score": edu_score})

        cert_score = weight("certifications") if certifications else 0
        items.append({"name": "certifications", "present": bool(certifications), "weight": weight("certifications"), "score": cert_score})

        pref_score = self._preferences_score(candidate, weight("preferences"))
        items.append({"name": "preferences", "present": pref_score == weight("preferences"), "weight": weight("preferences"), "score": pref_score})

        resume_score = weight("resumes") if resumes else 0
        items.append({"name": "resumes", "present": bool(resumes), "weight": weight("resumes"), "score": resume_score})

        total = sum(cast(int, item["score"]) for item in items)
        return {
            "total": total,
            "maximum": self.maximum,
            "percentage": round(100 * total / self.maximum) if self.maximum else 0,
            "items": items,
        }

    def _basic_score(self, candidate: Candidate, max_weight: int) -> int:
        required = [candidate.full_name, candidate.headline, candidate.email, candidate.current_role]
        filled = sum(1 for f in required if f)
        if max_weight == 0:
            return 0
        return round(max_weight * filled / len(required))

    def _preferences_score(self, candidate: Candidate, max_weight: int) -> int:
        prefs: dict[str, object] = candidate.career_preferences or {}
        required = ["target_roles", "preferred_locations", "work_mode"]
        filled = sum(1 for key in required if prefs.get(key))
        if max_weight == 0:
            return 0
        return round(max_weight * filled / len(required))
