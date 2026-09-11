"""Company schemas."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.models.company import CompanyVerificationStatus


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    website_domain: str | None
    careers_url: str | None
    verification_status: CompanyVerificationStatus
