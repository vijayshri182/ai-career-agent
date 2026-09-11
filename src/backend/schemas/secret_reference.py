"""Secret reference schemas.

Deliberately no field can carry a secret value: `external_reference` is an
identifier for the external secrets store, never the secret itself.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.models.secret_reference import SecretReferenceStatus, SecretType


class SecretReferenceRegister(BaseModel):
    provider_id: UUID
    secret_type: SecretType = SecretType.UNKNOWN
    external_reference: str
    notes: str | None = None


class SecretReferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    provider_id: UUID
    secret_type: SecretType
    external_reference: str
    status: SecretReferenceStatus
    rotated_at: datetime | None
    last_used_at: datetime | None
    notes: str | None


class SecretReferenceResolveRead(BaseModel):
    available: bool
    local_dev: bool
