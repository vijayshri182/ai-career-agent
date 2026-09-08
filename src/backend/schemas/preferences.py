"""Career preferences schema."""

from pydantic import BaseModel, ConfigDict

from backend.models.candidate import WorkMode


class CareerPreferences(BaseModel):
    model_config = ConfigDict(extra="allow")

    target_roles: list[str] = []
    target_industries: list[str] = []
    target_companies: list[str] = []
    excluded_companies: list[str] = []
    preferred_locations: list[str] = []
    work_mode: WorkMode | None = None
    min_compensation: int | None = None
    target_compensation: int | None = None
    max_compensation: int | None = None
    compensation_currency: str | None = None
    employment_type: str | None = None
    seniority: str | None = None
    travel_preference: str | None = None
    relocation_preference: str | None = None
    notice_period_days: int | None = None
