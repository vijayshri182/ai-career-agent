"""Certification service."""

from uuid import UUID

from backend.core.exceptions import NotFoundError
from backend.models.candidate import Certification
from backend.repositories.audit import AuditRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.certification import CertificationRepository
from backend.schemas.certification import CertificationCreate, CertificationUpdate


class CertificationService:
    def __init__(
        self,
        repo: CertificationRepository,
        audit_repo: AuditRepository,
        candidate_repo: CandidateRepository,
    ) -> None:
        self.repo = repo
        self.audit_repo = audit_repo
        self.candidate_repo = candidate_repo

    async def _assert_candidate_owned(self, candidate_id: UUID, user_id: UUID) -> None:
        await self.candidate_repo.get_for_user_or_404(candidate_id, user_id)

    async def list(self, candidate_id: UUID, user_id: UUID) -> list[Certification]:
        await self._assert_candidate_owned(candidate_id, user_id)
        return await self.repo.list_ordered(candidate_id)

    async def get(
        self, candidate_id: UUID, user_id: UUID, cert_id: UUID
    ) -> Certification:
        await self._assert_candidate_owned(candidate_id, user_id)
        cert = await self.repo.get(cert_id)
        if cert is None or cert.candidate_id != candidate_id:
            raise NotFoundError("Certification not found")
        return cert

    async def add(
        self, candidate_id: UUID, user_id: UUID, data: CertificationCreate
    ) -> Certification:
        await self._assert_candidate_owned(candidate_id, user_id)
        cert = await self.repo.create(candidate_id=candidate_id, **data.model_dump())
        await self.audit_repo.log(
            event_type="CERTIFICATION_ADDED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="Certification",
            entity_id=cert.id,
            metadata={"name": data.name},
        )
        return cert

    async def update(
        self, candidate_id: UUID, user_id: UUID, cert_id: UUID, data: CertificationUpdate
    ) -> Certification:
        cert = await self.get(candidate_id, user_id, cert_id)
        cert = await self.repo.update(cert, **data.model_dump(exclude_unset=True))
        await self.audit_repo.log(
            event_type="CERTIFICATION_UPDATED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="Certification",
            entity_id=cert.id,
        )
        return cert

    async def delete(self, candidate_id: UUID, user_id: UUID, cert_id: UUID) -> None:
        cert = await self.get(candidate_id, user_id, cert_id)
        await self.repo.delete(cert)
        await self.audit_repo.log(
            event_type="CERTIFICATION_DELETED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="Certification",
            entity_id=cert.id,
        )
