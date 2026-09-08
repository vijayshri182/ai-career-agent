"""Experience schemas."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


class ExperienceCreate(BaseModel):
    company_name: str
    title: str
    location: str | None = None
    start_date: date
    end_date: date | None = None
    is_current: bool = False
    description: str | None = None
    responsibilities: list[str] = []
    achievements: list[str] = []
    technologies: list[str] = []
    domain: str | None = None
    leadership_responsibilities: list[str] = []
    team_size: int | None = None
    display_order: int = 0

    @model_validator(mode="after")
    def check_dates(self) -> "ExperienceCreate":
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if self.is_current and self.end_date:
            raise ValueError("current role cannot have an end_date")
        return self


class ExperienceUpdate(BaseModel):
    company_name: str | None = None
    title: str | None = None
    location: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool | None = None
    description: str | None = None
    responsibilities: list[str] | None = None
    achievements: list[str] | None = None
    technologies: list[str] | None = None
    domain: str | None = None
    leadership_responsibilities: list[str] | None = None
    team_size: int | None = None
    display_order: int | None = None


class ExperienceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    company_name: str
    title: str
    location: str | None
    start_date: date
    end_date: date | None
    is_current: bool
    description: str | None
    responsibilities: list[str]
    achievements: list[str]
    technologies: list[str]
    domain: str | None
    leadership_responsibilities: list[str]
    team_size: int | None
    display_order: int
