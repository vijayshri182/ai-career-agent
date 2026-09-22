"""CP15 read-only matching evaluation over the existing matching engine.

Side-effect audit of the existing ACA matching service (performed for CP15):

* ``JobMatchingService.evaluate`` / ``batch_evaluate`` /
  ``score_for_orchestrator`` all funnel into ``_evaluate_and_persist`` which
  WRITES a ``JobMatch`` row (``match_repo.upsert``) and, for high matches, calls
  the notifier (writes a ``Notification`` row). They also require a
  ``JobMatchRepository`` and may change candidate-facing match state.
* The stateless components ``JobTextParser`` and ``JobMatchScorer`` perform NO
  I/O and NO writes (pure functions over in-memory data).

CP15 therefore DOES NOT invoke ``JobMatchingService`` (high risk of unintended
persistence). It uses a narrowly scoped adapter that loads the candidate
profile and the job read-only and calls the SAME ``JobTextParser`` and
``JobMatchScorer`` used in production, returning an in-memory outcome. No
``JobMatch``, ``Notification``, job, or candidate row is ever written. This is
"invoking the existing matching engine" without duplicating or copying any
matching calculation and without modifying matching.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from backend.models.candidate import Candidate, CandidateSkill, Experience
from backend.repositories.candidate import CandidateRepository
from backend.repositories.experience import ExperienceRepository
from backend.repositories.job import JobRepository
from backend.repositories.skill import SkillRepository
from backend.schemas.gate4e_eligibility import (
    Gate4eMatchEvaluationOutcome,
    Gate4eMatchEvaluationReport,
)
from backend.services.gate4e_eligibility import Gate4eEligibilityService
from backend.services.matching import (
    CandidateExperienceProfile,
    CandidateProfile,
    CandidateSkillProfile,
    JobMatchScorer,
    JobTextParser,
)


class Gate4eReadOnlyMatchEvaluator:
    """Evaluate only policy-eligible Gate 4E records; persist nothing."""

    def __init__(
        self,
        *,
        eligibility: Gate4eEligibilityService,
        candidate_repo: CandidateRepository,
        job_repo: JobRepository,
        skill_repo: SkillRepository,
        experience_repo: ExperienceRepository,
        scorer: JobMatchScorer | None = None,
        parser: JobTextParser | None = None,
    ) -> None:
        self._eligibility = eligibility
        self._candidate_repo = candidate_repo
        self._job_repo = job_repo
        self._skill_repo = skill_repo
        self._experience_repo = experience_repo
        self._scorer = scorer or JobMatchScorer()
        self._parser = parser or JobTextParser()

    async def evaluate_candidate(
        self, candidate_id: UUID, *, allow_partial_with_url: bool = False
    ) -> Gate4eMatchEvaluationReport:
        """Run eligibility, then read-only evaluation for eligible records."""
        eligibility = await self._eligibility.evaluate_candidate(
            candidate_id, allow_partial_with_url=allow_partial_with_url
        )

        outcomes: list[tuple[UUID, Gate4eMatchEvaluationOutcome]] = []
        for decision in eligibility.decisions:
            if not decision.eligible_for_matching or decision.job_id is None:
                continue
            outcome = await self.evaluate_job(candidate_id, decision.job_id)
            if outcome is not None:
                outcome.ingestion_identity = decision.ingestion_identity
                outcomes.append((decision.job_id, outcome))

        outcomes.sort(key=lambda pair: str(pair[0]))
        result = Gate4eMatchEvaluationReport(
            candidate_id=candidate_id,
            evaluated_at=datetime.now(UTC),
            eligibility=eligibility,
            evaluated_job_count=len(outcomes),
            outcomes=[outcome for _, outcome in outcomes],
        )
        return result

    async def evaluate_job(
        self, candidate_id: UUID, job_id: UUID
    ) -> Gate4eMatchEvaluationOutcome | None:
        """Pure, read-only score of one job for one candidate (no persistence)."""
        candidate = await self._candidate_repo.get(candidate_id)
        if candidate is None:
            return None
        job = await self._job_repo.get_for_candidate(job_id, candidate_id)
        if job is None:
            return None

        profile = await self._load_profile(candidate)
        job_view = self._parser.parse(
            title=job.title, location=job.location, description=job.description
        )
        output = self._scorer.score(profile, job_view)
        return Gate4eMatchEvaluationOutcome(
            job_id=job_id,
            rules_version=self._scorer.rules_version,
            score=output.score,
            confidence=output.confidence,
            is_match=output.is_match,
            matched_skills=output.matched_skills,
            missing_skills=output.missing_skills,
            transferable_skills=output.transferable_skills,
            strengths=output.strengths,
            gaps=output.gaps,
            blockers=output.blockers,
            breakdown=output.breakdown,
        )

    async def _load_profile(self, candidate: Candidate) -> CandidateProfile:
        """Mirror the production loader (data only; no matching logic)."""
        skills = await self._skill_repo.list_for_candidate(candidate.id)
        experiences = await self._experience_repo.list_ordered(candidate.id)
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
            skills=[
                CandidateSkillProfile(
                    name=skill.name,
                    proficiency=self._enum_value(skill.proficiency),
                    years_experience=skill.years_experience,
                    category=self._enum_value(skill.category),
                    is_primary=skill.is_primary,
                )
                for skill in skills
                if isinstance(skill, CandidateSkill)
            ],
            experiences=[
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
            ],
        )

    @staticmethod
    def _enum_value(value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        raw = getattr(value, "value", value)
        return str(raw) if raw is not None else None
