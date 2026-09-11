"""Secrets port and secret-reference service.

The application only ever stores *references* to secrets, never the secrets
themselves. `SecretsProvider` is the port the app depends on; a vault-backed
implementation can be injected in production. The local development
implementation (`LocalSecretsProvider`) deliberately never resolves a secret: it
reports "not available", guarantees nothing sensitive can leak from a dev
environment, and makes the absence of a vault explicit instead of silently
falling back to insecure storage.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from backend.core.exceptions import ValidationError
from backend.models.secret_reference import (
    SecretReference,
    SecretReferenceStatus,
    SecretType,
)
from backend.repositories.audit import AuditRepository
from backend.repositories.secret_reference import SecretReferenceRepository


@dataclass(frozen=True)
class SecretResolution:
    available: bool
    value: str | None = None


class SecretsProvider(Protocol):
    """Port for a secrets store. Implementations must never log the value."""

    name: str

    def resolve(self, reference: str) -> SecretResolution:
        """Resolve an external reference to a secret value."""
        ...


class LocalSecretsProvider:
    """Dev/test-only secrets provider.

    Never resolves a real secret. In production a vault-backed provider must be
    injected; this implementation makes accidental plaintext impossible by
    returning `available=False`.
    """

    name = "local-dev-placeholder"

    def resolve(self, reference: str) -> SecretResolution:  # noqa: ARG002
        return SecretResolution(available=False)


class SecretReferenceService:
    def __init__(
        self,
        repo: SecretReferenceRepository,
        audit_repo: AuditRepository,
        secrets_provider: SecretsProvider,
        actor_id: UUID,
        candidate_id: UUID,
    ) -> None:
        self.repo = repo
        self.audit_repo = audit_repo
        self.secrets_provider = secrets_provider
        self.actor_id = actor_id
        self.candidate_id = candidate_id

    async def register(
        self,
        provider_id: UUID,
        secret_type: SecretType,
        external_reference: str,
        notes: str | None = None,
    ) -> SecretReference:
        """Record a reference to a secret held elsewhere. The value itself is
        never accepted here — only an identifier for the external store.
        """
        if not external_reference or not external_reference.strip():
            raise ValidationError("An external reference is required")
        if len(external_reference) > 512:
            raise ValidationError("External reference is too long; pass an identifier only")
        ref = await self.repo.create(
            candidate_id=self.candidate_id,
            provider_id=provider_id,
            secret_type=secret_type,
            external_reference=external_reference.strip(),
            status=SecretReferenceStatus.ACTIVE,
            notes=notes,
        )
        await self.audit_repo.log(
            event_type="SECRET_REFERENCE_REGISTERED",
            actor_id=self.actor_id,
            candidate_id=self.candidate_id,
            entity_type="SecretReference",
            entity_id=ref.id,
            metadata={"provider_id": str(provider_id), "secret_type": secret_type.value},
        )
        return ref

    async def rotate(self, reference: SecretReference) -> SecretReference:
        if reference.status in (SecretReferenceStatus.REVOKED, SecretReferenceStatus.MISSING):
            raise ValidationError(f"Cannot rotate a {reference.status.value} reference")
        reference.status = SecretReferenceStatus.ROTATED
        reference.rotated_at = datetime.now(UTC)
        await self.repo.update(reference)
        await self.audit_repo.log(
            event_type="SECRET_REFERENCE_ROTATED",
            actor_id=self.actor_id,
            candidate_id=self.candidate_id,
            entity_type="SecretReference",
            entity_id=reference.id,
            metadata={"provider_id": str(reference.provider_id)},
        )
        return reference

    async def revoke(self, reference: SecretReference, reason: str | None = None) -> SecretReference:
        if reference.status == SecretReferenceStatus.REVOKED:
            return reference
        reference.status = SecretReferenceStatus.REVOKED
        await self.repo.update(reference)
        await self.audit_repo.log(
            event_type="SECRET_REFERENCE_REVOKED",
            actor_id=self.actor_id,
            candidate_id=self.candidate_id,
            entity_type="SecretReference",
            entity_id=reference.id,
            metadata={"provider_id": str(reference.provider_id), "reason": reason},
        )
        return reference

    async def resolve(self, reference: SecretReference) -> SecretResolution:
        """Resolve via the injected provider. Never logs the value."""
        resolution = self.secrets_provider.resolve(reference.external_reference)
        if resolution.available:
            reference.last_used_at = datetime.now(UTC)
            await self.repo.update(reference)
        return resolution

    async def get(self, reference_id: UUID) -> SecretReference:
        return await self.repo.get_for_candidate_or_404(reference_id, self.candidate_id)

    async def list(self, provider_id: UUID | None = None) -> list[SecretReference]:
        return await self.repo.list_by_candidate(self.candidate_id, provider_id=provider_id)
