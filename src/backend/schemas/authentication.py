"""Authentication provider schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.models.authentication import AuthenticationMethod, AuthProviderType, AuthState


class ProviderCreate(BaseModel):
    name: str
    provider_type: AuthProviderType = AuthProviderType.OTHER
    base_url: str | None = None
    authentication_method: AuthenticationMethod = AuthenticationMethod.UNKNOWN
    is_enabled: bool = True
    notes: str | None = None
    metadata: dict[str, object] = {}


class ProviderUpdate(BaseModel):
    name: str | None = None
    provider_type: AuthProviderType | None = None
    base_url: str | None = None
    authentication_method: AuthenticationMethod | None = None
    is_enabled: bool | None = None
    notes: str | None = None
    metadata: dict[str, object] | None = None


class ProviderStateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider_id: UUID
    status: AuthState
    session_reference: str | None
    checked_at: datetime
    authenticated_at: datetime | None
    state_metadata: dict[str, object]


class ProviderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    name: str
    provider_type: AuthProviderType
    base_url: str | None
    authentication_method: AuthenticationMethod
    is_enabled: bool
    notes: str | None
    metadata_json: dict[str, object]
    created_at: datetime
    updated_at: datetime


class AuthOverview(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider_count: int
    open_challenge_count: int
    providers: list["ProviderOverviewRead"]
    open_challenges: list["ChallengeSummaryRead"]


class ProviderOverviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    provider_type: str
    authentication_method: str
    is_enabled: bool
    auth_status: str
    authenticated_at: datetime | None
    last_checked: datetime
    session_reference: str | None


class AuthStateReport(BaseModel):
    status: AuthState
    metadata: dict[str, object] = {}
    session_reference: str | None = None


class ChallengeSummaryRead(BaseModel):
    id: UUID
    provider_id: UUID
    challenge_type: str
    status: str
    severity: str
    human_required: bool
    detected_at: datetime
    expires_at: datetime | None
