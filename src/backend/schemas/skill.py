"""Skill schemas."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.models.candidate import Proficiency, SkillCategory


class SkillCreate(BaseModel):
    name: str
    category: SkillCategory = SkillCategory.OTHER
    proficiency: Proficiency = Proficiency.INTERMEDIATE
    years_experience: int | None = None
    last_used_year: int | None = None
    is_primary: bool = False


class SkillUpdate(BaseModel):
    name: str | None = None
    category: SkillCategory | None = None
    proficiency: Proficiency | None = None
    years_experience: int | None = None
    last_used_year: int | None = None
    is_primary: bool | None = None


class SkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    name: str
    category: SkillCategory
    proficiency: Proficiency
    years_experience: int | None
    last_used_year: int | None
    is_primary: bool
