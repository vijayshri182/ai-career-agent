"""Secret reference model.

A SecretReference is a *pointer* to a secret held in an external secrets
provider (vault, env, OS keyring, ...). The raw secret value is never stored in
the application database, in logs, in schemas, or in tests. Local development
uses a dev-safe secrets provider that returns placeholders only.
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, Column, DateTime, String
from sqlmodel import Field, Relationship

from backend.db.base import IdModel

if TYPE_CHECKING:
    from backend.models.authentication import AuthProvider
    from backend.models.candidate import Candidate


class SecretType(str, Enum):
    PASSWORD = "password"
    API_KEY = "api_key"
    OAUTH_TOKEN = "oauth_token"
    REFRESH_TOKEN = "refresh_token"
    SESSION_COOKIE = "session_cookie"
    MFA_SHARED_SECRET = "mfa_shared_secret"
    UNKNOWN = "unknown"


class SecretReferenceStatus(str, Enum):
    ACTIVE = "active"
    ROTATED = "rotated"
    REVOKED = "revoked"
    MISSING = "missing"


class SecretReference(IdModel, table=True):
    __tablename__ = "secret_references"

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    provider_id: UUID = Field(foreign_key="auth_providers.id", nullable=False, index=True)
    secret_type: SecretType = Field(default=SecretType.UNKNOWN)
    # Identifier usable by the secrets provider — never the secret itself.
    external_reference: str = Field(sa_column=Column(String(512), nullable=False))
    status: SecretReferenceStatus = Field(default=SecretReferenceStatus.ACTIVE)
    rotated_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    last_used_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    notes: str | None = Field(sa_column=Column(String(512), nullable=True))
    is_local_dev_placeholder: bool = Field(
        default=False, sa_column=Column(Boolean, nullable=False)
    )

    candidate: "Candidate" = Relationship(back_populates="secret_references")
    provider: "AuthProvider" = Relationship(back_populates="secret_references")
