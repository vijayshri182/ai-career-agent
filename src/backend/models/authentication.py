"""Authentication provider and state models.

These entities are provider/site neutral. They describe *where* the agent may
need to authenticate and *what* the current authentication state is. They never
contain raw passwords, OTPs, cookies, tokens, or any other secret value — only
secure references/identifiers to such values held in an external secrets
provider or encrypted browser-state storage.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import JSON, Boolean, Column, DateTime, String, Text
from sqlmodel import Field, Relationship, UniqueConstraint

from backend.db.base import IdModel

if TYPE_CHECKING:
    from backend.models.browser_session import BrowserSession
    from backend.models.candidate import Candidate
    from backend.models.challenge import Challenge
    from backend.models.secret_reference import SecretReference
    from backend.models.workflow_run import WorkflowRun


class AuthenticationMethod(str, Enum):
    """How a provider expects the candidate to authenticate."""

    NONE = "none"
    SESSION = "session"
    OAUTH = "oauth"
    OIDC = "oidc"
    PASSWORD = "password"
    API_KEY = "api_key"
    UNKNOWN = "unknown"


class AuthProviderType(str, Enum):
    """High-level category of the external site."""

    ATS = "ats"
    CAREER_SITE = "career_site"
    JOB_BOARD = "job_board"
    NETWORKING = "networking"
    EMAIL = "email"
    OTHER = "other"


class AuthState(str, Enum):
    """Current authentication state for a provider."""

    NOT_REQUIRED = "not_required"
    NOT_CONFIGURED = "not_configured"
    AUTHENTICATED = "authenticated"
    SESSION_EXPIRED = "session_expired"
    AUTHENTICATION_REQUIRED = "authentication_required"
    MFA_REQUIRED = "mfa_required"
    CAPTCHA_REQUIRED = "captcha_required"
    ACCESS_BLOCKED = "access_blocked"
    RATE_LIMITED = "rate_limited"
    HUMAN_ACTION_REQUIRED = "human_action_required"
    ERROR = "error"


class AuthProvider(IdModel, table=True):
    """A site the candidate may need to authenticate to (site-neutral)."""

    __tablename__ = "auth_providers"
    __table_args__ = (
        UniqueConstraint("candidate_id", "name", name="uq_auth_providers_candidate_name"),
    )

    candidate_id: UUID = Field(foreign_key="candidates.id", nullable=False, index=True)
    name: str = Field(sa_column=Column(String(128), nullable=False))
    provider_type: AuthProviderType = Field(default=AuthProviderType.OTHER)
    base_url: str | None = Field(sa_column=Column(String(512), nullable=True))
    authentication_method: AuthenticationMethod = Field(default=AuthenticationMethod.UNKNOWN)
    is_enabled: bool = Field(default=True, sa_column=Column(Boolean, nullable=False))
    notes: str | None = Field(sa_column=Column(Text, nullable=True))
    metadata_json: dict[str, object] = Field(
        default_factory=dict, sa_column=Column(JSON, default=dict)
    )

    candidate: "Candidate" = Relationship(back_populates="auth_providers")
    state: "AuthProviderState" = Relationship(
        back_populates="provider", sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"}
    )
    challenges: list["Challenge"] = Relationship(
        back_populates="provider", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    secret_references: list["SecretReference"] = Relationship(
        back_populates="provider", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    browser_sessions: list["BrowserSession"] = Relationship(
        back_populates="provider", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    workflow_runs: list["WorkflowRun"] = Relationship(
        back_populates="provider", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


class AuthProviderState(IdModel, table=True):
    """Current authentication state for one provider (1:1).

    Stores only state and secure references — never secrets. Session references
    are opaque identifiers managed by an external secrets/browser-state store.
    """

    __tablename__ = "auth_provider_states"

    provider_id: UUID = Field(
        foreign_key="auth_providers.id", nullable=False, index=True, unique=True
    )
    status: AuthState = Field(default=AuthState.NOT_CONFIGURED, index=True)
    session_reference: str | None = Field(sa_column=Column(String(512), nullable=True))
    checked_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": False},  # type: ignore[call-overload]
    )
    authenticated_at: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    state_metadata: dict[str, object] = Field(
        default_factory=dict, sa_column=Column(JSON, default=dict)
    )

    provider: "AuthProvider" = Relationship(back_populates="state")
