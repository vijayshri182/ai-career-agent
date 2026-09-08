"""Profile aggregation service."""

from uuid import UUID

from backend.core.config import get_settings
from backend.core.exceptions import NotFoundError
from backend.repositories.candidate import CandidateRepository
from backend.repositories.certification import CertificationRepository
from backend.repositories.education import EducationRepository
from backend.repositories.experience import ExperienceRepository
from backend.repositories.resume import ResumeRepository
from backend.repositories.skill import SkillRepository
from backend.services.completeness import ProfileCompletenessService


class ProfileService:
    """Aggregates candidate profile data for the dashboard."""

    def __init__(
        self,
        candidate_repo: CandidateRepository,
        skill_repo: SkillRepository,
        experience_repo: ExperienceRepository,
        education_repo: EducationRepository,
        certification_repo: CertificationRepository,
        resume_repo: ResumeRepository,
    ) -> None:
        self.candidate_repo = candidate_repo
        self.skill_repo = skill_repo
        self.experience_repo = experience_repo
        self.education_repo = education_repo
        self.certification_repo = certification_repo
        self.resume_repo = resume_repo
        self.completeness = ProfileCompletenessService(get_settings())

    async def get_profile(self, user_id: UUID) -> dict[str, object]:
        candidate = await self.candidate_repo.get_active_by_user(user_id)
        if candidate is None:
            raise NotFoundError("Candidate profile not found")

        skills = await self.skill_repo.list(candidate_id=candidate.id)
        experiences = await self.experience_repo.list_ordered(candidate.id)
        educations = await self.education_repo.list_ordered(candidate.id)
        certifications = await self.certification_repo.list_ordered(candidate.id)
        resumes = await self.resume_repo.list_active(candidate.id)

        completeness = self.completeness.calculate(
            candidate, skills, experiences, educations, certifications, resumes
        )

        return {
            "candidate": candidate,
            "skills": skills,
            "experiences": experiences,
            "educations": educations,
            "certifications": certifications,
            "resumes": resumes,
            "completeness": completeness,
        }
