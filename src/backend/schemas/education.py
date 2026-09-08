"""Education schemas."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


class EducationCreate(BaseModel):
    institution: str
    degree: str
    field_of_study: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    grade: str | None = None
    description: str | None = None
    display_order: int = 0

    @model_validator(mode="after")
    def check_dates(self) -> "EducationCreate":
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class EducationUpdate(BaseModel):
    institution: str | None = None
    degree: str | None = None
    field_of_study: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    grade: str | None = None
    description: str | None = None
    display_order: int | None = None


class EducationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    institution: str
    degree: str
    field_of_study: str | None
    start_date: date | None
    end_date: date | None
    grade: str | None
    description: str | None
    display_order: int
