"""Certification schemas."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


class CertificationCreate(BaseModel):
    name: str
    issuing_organization: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    credential_id: str | None = None
    credential_url: str | None = None
    display_order: int = 0

    @model_validator(mode="after")
    def check_dates(self) -> "CertificationCreate":
        if self.expiry_date and self.issue_date and self.expiry_date < self.issue_date:
            raise ValueError("expiry_date must be on or after issue_date")
        return self


class CertificationUpdate(BaseModel):
    name: str | None = None
    issuing_organization: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    credential_id: str | None = None
    credential_url: str | None = None
    display_order: int | None = None


class CertificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    name: str
    issuing_organization: str | None
    issue_date: date | None
    expiry_date: date | None
    credential_id: str | None
    credential_url: str | None
    display_order: int
