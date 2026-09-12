"""Learning / optimization service (Phase 12).

Produces explainable analytics and purely suggestive recommendations from
candidate-owned data. Hard invariants:

* ``Feedback`` only records observed outcomes; it never infers a cause.
* ``Recommendation`` rows never edit anything: they carry an explicit rationale
  list citing the exact candidate-owned facts they were derived from, and the
  candidate acts on them through the normal profile/approval APIs.
* Recommendations are derived only from neutral signals (skills, matches,
  counts). No protected attribute is collected, and a runtime guard rejects any
  recommendation that would reference one.
"""

import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from backend.core.exceptions import NotFoundError, ValidationError
from backend.models.application import Application, ApplicationStatus
from backend.models.job_match import JobMatchStatus
from backend.models.learning import (
    Feedback,
    FeedbackOutcome,
    Recommendation,
    RecommendationKind,
    RecommendationStatus,
)
from backend.models.outreach import OutreachMessage, OutreachStatus
from backend.repositories.application import ApplicationRepository
from backend.repositories.audit import AuditRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.certification import CertificationRepository
from backend.repositories.education import EducationRepository
from backend.repositories.experience import ExperienceRepository
from backend.repositories.job import JobRepository
from backend.repositories.job_match import JobMatchRepository
from backend.repositories.learning import FeedbackRepository, RecommendationRepository
from backend.repositories.outreach import OutreachMessageRepository
from backend.repositories.skill import SkillRepository
from backend.schemas.learning import (
    AnalyticsSummary,
    ApplicationFunnel,
    FeedbackAnalytics,
    MatchAnalytics,
    OutreachAnalytics,
    ProfileMetrics,
)

# Bias/fairness guard: recommendations may only derive from neutral,
# candidate-owned signals. These terms are never collected nor used.
PROTECTED_ATTRIBUTE_TERMS = frozenset(
    {
        "race",
        "gender",
        "sex",
        "age",
        "ethnic",
        "religion",
        "nationality",
        "marital",
        "pregnancy",
        "disability",
        "sexual",
        "orientation",
        "origin",
    }
)

SKILL_GAP_RECOMMENDATION_LIMIT = 3
TOP_MISSING_SKILLS_LIMIT = 5
MIN_SKILLS_RECOMMENDATION = 3
OUTREACH_LOW_RESPONSE_RATE = 0.25
_WORD_RE = re.compile(r"[a-z]+")


@dataclass(frozen=True)
class _DraftRecommendation:
    kind: RecommendationKind
    source_key: str
    title: str
    detail: str
    rationale: list[str]


class AnalyticsService:
    def __init__(
        self,
        *,
        candidate_repo: CandidateRepository,
        job_repo: JobRepository,
        match_repo: JobMatchRepository,
        application_repo: ApplicationRepository,
        skill_repo: SkillRepository,
        experience_repo: ExperienceRepository,
        education_repo: EducationRepository,
        certification_repo: CertificationRepository,
        message_repo: OutreachMessageRepository,
        feedback_repo: FeedbackRepository,
        recommendation_repo: RecommendationRepository,
        audit_repo: AuditRepository,
        actor_id: UUID,
        candidate_id: UUID,
    ) -> None:
        self._candidates = candidate_repo
        self._jobs = job_repo
        self._matches = match_repo
        self._applications = application_repo
        self._skills = skill_repo
        self._experiences = experience_repo
        self._educations = education_repo
        self._certifications = certification_repo
        self._messages = message_repo
        self._feedback = feedback_repo
        self._recommendations = recommendation_repo
        self._audit = audit_repo
        self._actor_id = actor_id
        self._candidate_id = candidate_id

    # ------------------------------------------------------------- ownership

    async def _ensure_owned_candidate(self) -> None:
        await self._candidates.get_for_user_or_404(self._candidate_id, self._actor_id)

    async def _owned_application(self, application_id: UUID) -> Application:
        application = await self._applications.get_for_candidate(
            application_id, self._candidate_id
        )
        if application is None:
            raise NotFoundError("Application not found")
        return application

    async def _owned_outreach_message(self, message_id: UUID) -> OutreachMessage:
        message = await self._messages.get_for_candidate(message_id, self._candidate_id)
        if message is None:
            raise NotFoundError("Outreach message not found")
        return message

    async def _owned_recommendation(self, recommendation_id: UUID) -> Recommendation:
        recommendation = await self._recommendations.get_for_candidate(
            recommendation_id, self._candidate_id
        )
        if recommendation is None:
            raise NotFoundError("Recommendation not found")
        return recommendation

    # ---------------------------------------------------------------- summary

    async def summary(self) -> AnalyticsSummary:
        await self._ensure_owned_candidate()
        cid = self._candidate_id

        app_counts = await self._applications.count_by_status(cid)
        applications = ApplicationFunnel(
            total=sum(app_counts.values()),
            draft=app_counts.get(ApplicationStatus.DRAFT, 0),
            ready=app_counts.get(ApplicationStatus.READY, 0),
            submitted=app_counts.get(ApplicationStatus.SUBMITTED, 0),
            withdrawn=app_counts.get(ApplicationStatus.WITHDRAWN, 0),
        )

        matches = await self._matches.list_for_candidate(cid, limit=10000, offset=0)
        scores = [m.score for m in matches]
        confidences = [m.confidence for m in matches]
        missing_counter: Counter[str] = Counter()
        for match in matches:
            for skill in match.missing_skills or []:
                key = skill.strip().lower()
                if key:
                    missing_counter[key] += 1
        match_analytics = MatchAnalytics(
            total=len(matches),
            matched=await self._matches.count_for_candidate(cid, is_match=True),
            rejected=await self._matches.count_for_candidate(cid, status=JobMatchStatus.REJECTED),
            pending=await self._matches.count_for_candidate(cid, status=JobMatchStatus.PENDING),
            avg_score=round(sum(scores) / len(scores), 3) if scores else None,
            avg_confidence=round(sum(confidences) / len(confidences), 3)
            if confidences
            else None,
            top_missing_skills=[skill for skill, _ in missing_counter.most_common(TOP_MISSING_SKILLS_LIMIT)],
        )

        message_counts = await self._messages.count_by_status(cid)
        sent = message_counts.get(OutreachStatus.SENT, 0)
        responded = await self._messages.count_responded(cid)
        outreach = OutreachAnalytics(
            sent=sent,
            responded=responded,
            response_rate=round(responded / sent, 3) if sent else None,
        )

        feedback_total = await self._feedback.count_for_candidate(cid)
        by_outcome = await self._feedback.count_by_outcome(cid)
        feedback = FeedbackAnalytics(
            total=feedback_total,
            by_outcome={outcome.value: count for outcome, count in by_outcome.items()},
        )

        profile = ProfileMetrics(
            skills_count=len(await self._skills.list_for_candidate(cid)),
            experiences_count=len(await self._experiences.list_ordered(cid)),
            educations_count=len(await self._educations.list_ordered(cid)),
            certifications_count=len(await self._certifications.list_ordered(cid)),
            jobs_count=await self._jobs.count_for_candidate(cid),
        )

        return AnalyticsSummary(
            applications=applications,
            matches=match_analytics,
            outreach=outreach,
            feedback=feedback,
            profile=profile,
            generated_at=datetime.now(UTC),
        )

    # ---------------------------------------------------------------- feedback

    async def add_feedback(
        self,
        *,
        outcome: FeedbackOutcome,
        application_id: UUID | None = None,
        outreach_message_id: UUID | None = None,
        stage: str | None = None,
        note: str | None = None,
    ) -> Feedback:
        await self._ensure_owned_candidate()
        if application_id is not None:
            await self._owned_application(application_id)
        if outreach_message_id is not None:
            await self._owned_outreach_message(outreach_message_id)
        feedback = await self._feedback.create(
            candidate_id=self._candidate_id,
            outcome=outcome,
            application_id=application_id,
            outreach_message_id=outreach_message_id,
            stage=stage,
            note=note,
        )
        await self._audit.log(
            "feedback.recorded",
            actor_id=self._actor_id,
            candidate_id=self._candidate_id,
            entity_type="feedback",
            entity_id=feedback.id,
            metadata={"outcome": outcome.value},
        )
        return feedback

    async def list_feedback(
        self,
        *,
        outcome: FeedbackOutcome | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Feedback], int]:
        await self._ensure_owned_candidate()
        items = await self._feedback.list_for_candidate(
            self._candidate_id, outcome=outcome, limit=limit, offset=offset
        )
        total = await self._feedback.count_for_candidate(
            self._candidate_id, outcome=outcome
        )
        return items, total

    # ---------------------------------------------------------- recommendations

    async def _compute_recommendations(self) -> list[_DraftRecommendation]:
        cid = self._candidate_id
        drafts: list[_DraftRecommendation] = []

        skills = await self._skills.list_for_candidate(cid)
        skill_names = {skill.name.strip().lower() for skill in skills}
        matches = await self._matches.list_for_candidate(cid, limit=10000, offset=0)

        missing_counter: Counter[str] = Counter()
        for match in matches:
            for skill in match.missing_skills or []:
                key = skill.strip().lower()
                if key and key not in skill_names:
                    missing_counter[key] += 1
        for skill, count in missing_counter.most_common(SKILL_GAP_RECOMMENDATION_LIMIT):
            drafts.append(
                _DraftRecommendation(
                    kind=RecommendationKind.SKILL_GAP,
                    source_key=f"skill:{skill}",
                    title=f"Learn {skill}",
                    detail=(
                        f"Add {skill} to your profile and to tailored documents — it was flagged as "
                        f"missing for {count} job match(es) you have."
                    ),
                    rationale=[
                        f"{skill} appears in the missing-skills data of {count} job match(es)."
                    ],
                )
            )

        experiences = await self._experiences.list_ordered(cid)
        educations = await self._educations.list_ordered(cid)
        certifications = await self._certifications.list_ordered(cid)
        if not experiences:
            drafts.append(
                _DraftRecommendation(
                    kind=RecommendationKind.PROFILE_IMPROVEMENT,
                    source_key="experience:missing",
                    title="Add your work experience",
                    detail=(
                        "Record your work experience so opportunities can be matched against "
                        "what you have actually done."
                    ),
                    rationale=[f"Your profile has {len(experiences)} work experience record(s)."],
                )
            )
        if not educations:
            drafts.append(
                _DraftRecommendation(
                    kind=RecommendationKind.PROFILE_IMPROVEMENT,
                    source_key="education:missing",
                    title="Add your education",
                    detail="Record your education to strengthen profile completeness.",
                    rationale=[f"Your profile has {len(educations)} education record(s)."],
                )
            )
        if not certifications:
            drafts.append(
                _DraftRecommendation(
                    kind=RecommendationKind.PROFILE_IMPROVEMENT,
                    source_key="certification:missing",
                    title="Add your certifications",
                    detail="Record certifications you hold to strengthen profile completeness.",
                    rationale=[f"Your profile has {len(certifications)} certification record(s)."],
                )
            )
        if len(skills) < MIN_SKILLS_RECOMMENDATION:
            drafts.append(
                _DraftRecommendation(
                    kind=RecommendationKind.PROFILE_IMPROVEMENT,
                    source_key="skills:low",
                    title="Complete your skills list",
                    detail="Add the main technologies and tools you use to help matching.",
                    rationale=[
                        f"Only {len(skills)} skill(s) are recorded on your profile."
                    ],
                )
            )

        app_counts = await self._applications.count_by_status(cid)
        submitted = app_counts.get(ApplicationStatus.SUBMITTED, 0)
        feedback_total = await self._feedback.count_for_candidate(cid)
        if submitted > 0 and feedback_total == 0:
            drafts.append(
                _DraftRecommendation(
                    kind=RecommendationKind.APPLY_OPTIMIZATION,
                    source_key="feedback:no_outcomes",
                    title="Track application outcomes",
                    detail=(
                        "Record what happens after you submit applications (interview, offer, "
                        "rejection, or no response) so the system can learn which efforts pay off."
                    ),
                    rationale=[
                        f"You have {submitted} submitted application(s) and {feedback_total} "
                        "recorded outcome(s)."
                    ],
                )
            )

        jobs_count = await self._jobs.count_for_candidate(cid)
        matched_count = await self._matches.count_for_candidate(cid, is_match=True)
        if jobs_count > 0 and matched_count == 0:
            drafts.append(
                _DraftRecommendation(
                    kind=RecommendationKind.SOURCE_OPTIMIZATION,
                    source_key="source:no_matches",
                    title="Review your job discovery sources",
                    detail=(
                        "You have discovered jobs but none matched your profile yet. Review "
                        "discovery filters and profile completeness together."
                    ),
                    rationale=[
                        f"{jobs_count} discovered job(s) and {matched_count} matched so far."
                    ],
                )
            )

        message_counts = await self._messages.count_by_status(cid)
        sent = message_counts.get(OutreachStatus.SENT, 0)
        responded = await self._messages.count_responded(cid)
        if sent > 0 and (responded == 0 or responded / sent < OUTREACH_LOW_RESPONSE_RATE):
            no_responses = responded == 0
            drafts.append(
                _DraftRecommendation(
                    kind=RecommendationKind.OUTREACH_OPTIMIZATION,
                    source_key=f"outreach:{'no_responses' if no_responses else 'low_response'}",
                    title="Review your outreach approach" if no_responses else "Improve outreach response rate",
                    detail=(
                        "Consider reviewing messaging, follow-up cadence, and whether verified "
                        "contacts are delivering responses."
                    ),
                    rationale=[
                        f"{sent} outreach message(s) sent and {responded} response(s) recorded."
                    ],
                )
            )

        return drafts

    @staticmethod
    def _assert_fair(drafts: list[_DraftRecommendation]) -> None:
        for draft in drafts:
            text = (
                draft.title + " " + draft.detail + " " + " ".join(draft.rationale)
            ).casefold()
            tokens = set(_WORD_RE.findall(text))
            disallowed = tokens & PROTECTED_ATTRIBUTE_TERMS
            if disallowed:
                raise ValidationError(
                    f"Recommendation {draft.source_key} would reference a protected attribute"
                )

    async def generate_recommendations(self, *, refresh: bool = False) -> list[Recommendation]:
        await self._ensure_owned_candidate()
        drafts = await self._compute_recommendations()
        self._assert_fair(drafts)
        fresh_keys = {(draft.kind, draft.source_key) for draft in drafts}

        if refresh:
            active = await self._recommendations.list_for_candidate(
                self._candidate_id, status=RecommendationStatus.ACTIVE
            )
            for recommendation in active:
                if (recommendation.kind, recommendation.source_key) not in fresh_keys:
                    await self._recommendations.update(
                        recommendation, status=RecommendationStatus.ARCHIVED
                    )

        for draft in drafts:
            existing = await self._recommendations.get_by_key(
                self._candidate_id, draft.kind, draft.source_key
            )
            if existing is not None:
                continue
            recommendation = await self._recommendations.create(
                candidate_id=self._candidate_id,
                kind=draft.kind,
                source_key=draft.source_key,
                title=draft.title,
                detail=draft.detail,
                rationale=draft.rationale,
                status=RecommendationStatus.ACTIVE,
            )
            await self._audit.log(
                "recommendation.generated",
                actor_id=self._actor_id,
                candidate_id=self._candidate_id,
                entity_type="recommendation",
                entity_id=recommendation.id,
                metadata={"kind": draft.kind.value, "source_key": draft.source_key},
            )

        return await self._recommendations.list_for_candidate(
            self._candidate_id, status=RecommendationStatus.ACTIVE
        )

    async def list_recommendations(
        self,
        *,
        status: RecommendationStatus | None = None,
        kind: RecommendationKind | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Recommendation], int]:
        await self._ensure_owned_candidate()
        items = await self._recommendations.list_for_candidate(
            self._candidate_id, status=status, kind=kind, limit=limit, offset=offset
        )
        total = await self._recommendations.count_for_candidate(
            self._candidate_id, status=status, kind=kind
        )
        return items, total

    async def acknowledge(self, recommendation_id: UUID) -> Recommendation:
        await self._ensure_owned_candidate()
        recommendation = await self._owned_recommendation(recommendation_id)
        if recommendation.status == RecommendationStatus.ARCHIVED:
            raise ValidationError("Cannot acknowledge an archived recommendation")
        if recommendation.status == RecommendationStatus.ACTIVE:
            recommendation = await self._recommendations.update(
                recommendation, status=RecommendationStatus.ACKNOWLEDGED
            )
        await self._audit.log(
            "recommendation.acknowledged",
            actor_id=self._actor_id,
            candidate_id=self._candidate_id,
            entity_type="recommendation",
            entity_id=recommendation.id,
        )
        return recommendation

    async def archive(self, recommendation_id: UUID) -> Recommendation:
        await self._ensure_owned_candidate()
        recommendation = await self._owned_recommendation(recommendation_id)
        if recommendation.status != RecommendationStatus.ARCHIVED:
            recommendation = await self._recommendations.update(
                recommendation, status=RecommendationStatus.ARCHIVED
            )
        await self._audit.log(
            "recommendation.archived",
            actor_id=self._actor_id,
            candidate_id=self._candidate_id,
            entity_type="recommendation",
            entity_id=recommendation.id,
        )
        return recommendation
