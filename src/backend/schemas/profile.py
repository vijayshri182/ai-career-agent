"""Profile aggregation schemas."""


from pydantic import BaseModel, ConfigDict

from backend.schemas.candidate import CandidateRead
from backend.schemas.certification import CertificationRead
from backend.schemas.education import EducationRead
from backend.schemas.experience import ExperienceRead
from backend.schemas.resume import ResumeRead
from backend.schemas.skill import SkillRead


class ProfileCompletenessItem(BaseModel):
    name: str
    present: bool
    weight: int
    score: int


class ProfileCompleteness(BaseModel):
    total: int
    maximum: int
    percentage: int
    items: list[ProfileCompletenessItem]


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    candidate: CandidateRead
    skills: list[SkillRead]
    experiences: list[ExperienceRead]
    educations: list[EducationRead]
    certifications: list[CertificationRead]
    resumes: list[ResumeRead]
    completeness: ProfileCompleteness
