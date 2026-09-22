"""Recruiter signal service (domain/persistence only).

This service records evidence-backed signals and moves them through an explicit
lifecycle. It never generates signals, never discovers or contacts recruiters,
and never issues outreach. Ownership rules match the other candidate-scoped
services: every operation requires the calling user to own the candidate.
"""

import hashlib
import json
from uuid import UUID

from backend.core.exceptions import NotFoundError, ValidationError
from backend.models.recruiter_contact import RecruiterContact
from backend.models.recruiter_signal import (
    RecruiterSignal,
    RecruiterSignalStatus,
    RecruiterSignalType,
)
from backend.repositories.audit import AuditRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.company import CompanyRepository
from backend.repositories.job import JobRepository
from backend.repositories.recruiter_contact import RecruiterContactRepository
from backend.repositories.recruiter_signal import RecruiterSignalRepository
from backend.schemas.recruiter_signal import RecruiterSignalCreate

_ALLOWED_TRANSITIONS: dict[RecruiterSignalStatus, set[RecruiterSignalStatus]] = {
    RecruiterSignalStatus.DISCOVERED: {
        RecruiterSignalStatus.EVIDENCE_PENDING,
        RecruiterSignalStatus.READY_FOR_REVIEW,
        RecruiterSignalStatus.REJECTED,
        RecruiterSignalStatus.EXPIRED,
    },
    RecruiterSignalStatus.EVIDENCE_PENDING: {
        RecruiterSignalStatus.READY_FOR_REVIEW,
        RecruiterSignalStatus.REJECTED,
        RecruiterSignalStatus.EXPIRED,
    },
    RecruiterSignalStatus.READY_FOR_REVIEW: {
        RecruiterSignalStatus.APPROVED,
        RecruiterSignalStatus.REJECTED,
        RecruiterSignalStatus.EXPIRED,
    },
    RecruiterSignalStatus.APPROVED: {RecruiterSignalStatus.EXPIRED},
    RecruiterSignalStatus.REJECTED: {RecruiterSignalStatus.EXPIRED},
    RecruiterSignalStatus.EXPIRED: set(),
}


class RecruiterSignalService:
    def __init__(
        self,
        signal_repo: RecruiterSignalRepository,
        contact_repo: RecruiterContactRepository,
        job_repo: JobRepository,
        company_repo: CompanyRepository,
        candidate_repo: CandidateRepository,
        audit_repo: AuditRepository,
    ) -> None:
        self.signal_repo = signal_repo
        self.contact_repo = contact_repo
        self.job_repo = job_repo
        self.company_repo = company_repo
        self.candidate_repo = candidate_repo
        self.audit_repo = audit_repo

    async def _assert_candidate_owned(self, candidate_id: UUID, user_id: UUID) -> None:
        await self.candidate_repo.get_for_user_or_404(candidate_id, user_id)

    @staticmethod
    def _signal_identity(
        candidate_id: UUID,
        job_id: UUID,
        recruiter_contact_id: UUID | None,
        signal_type: RecruiterSignalType,
        source: str,
        source_reference: str | None,
    ) -> str:
        canonical = json.dumps(
            {
                "candidate_id": str(candidate_id),
                "job_id": str(job_id),
                "recruiter_contact_id": (
                    str(recruiter_contact_id) if recruiter_contact_id is not None else None
                ),
                "signal_type": signal_type.value,
                "source": source,
                "source_reference": source_reference,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def create_signal(
        self, candidate_id: UUID, user_id: UUID, data: RecruiterSignalCreate
    ) -> RecruiterSignal:
        await self._assert_candidate_owned(candidate_id, user_id)

        job = await self.job_repo.get_for_candidate(data.job_id, candidate_id)
        if job is None:
            raise NotFoundError("Job not found")

        contact: RecruiterContact | None = None
        if data.recruiter_contact_id is not None:
            contact = await self.contact_repo.get_for_candidate(
                data.recruiter_contact_id, candidate_id
            )
            if contact is None:
                raise NotFoundError("Recruiter contact not found")

        if data.company_id is not None:
            company = await self.company_repo.get(data.company_id)
            if company is None:
                raise NotFoundError("Company not found")

        self._validate_coherence(data.signal_type, contact)

        identity = self._signal_identity(
            candidate_id,
            data.job_id,
            data.recruiter_contact_id,
            data.signal_type,
            data.source,
            data.source_reference,
        )
        existing = await self.signal_repo.find_by_identity(candidate_id, identity)
        if existing is not None:
            return existing

        signal = await self.signal_repo.create(
            candidate_id=candidate_id,
            job_id=data.job_id,
            recruiter_contact_id=data.recruiter_contact_id,
            company_id=data.company_id,
            signal_type=data.signal_type,
            status=RecruiterSignalStatus.DISCOVERED,
            signal_identity=identity,
            source=data.source,
            source_reference=data.source_reference,
            evidence_json=data.evidence or {},
            provenance_json=data.provenance or {},
        )
        await self.audit_repo.log(
            event_type="RECRUITER_SIGNAL_CREATED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="RecruiterSignal",
            entity_id=signal.id,
            metadata={
                "signal_type": data.signal_type.value,
                "signal_identity": identity,
            },
        )
        return signal

    async def update_status(
        self,
        candidate_id: UUID,
        user_id: UUID,
        signal_id: UUID,
        new_status: RecruiterSignalStatus,
    ) -> RecruiterSignal:
        await self._assert_candidate_owned(candidate_id, user_id)
        signal = await self.signal_repo.get_for_candidate(signal_id, candidate_id)
        if signal is None:
            raise NotFoundError("Recruiter signal not found")

        if signal.status is new_status:
            return signal

        allowed = _ALLOWED_TRANSITIONS.get(signal.status, set())
        if new_status not in allowed:
            raise ValidationError(
                f"Cannot transition recruiter signal from {signal.status.value} "
                f"to {new_status.value}"
            )

        previous = signal.status
        updated = await self.signal_repo.update(signal, status=new_status)
        await self.audit_repo.log(
            event_type="RECRUITER_SIGNAL_STATUS_CHANGED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="RecruiterSignal",
            entity_id=signal.id,
            metadata={"from": previous.value, "to": new_status.value},
        )
        return updated

    async def get_signal(
        self, candidate_id: UUID, user_id: UUID, signal_id: UUID
    ) -> RecruiterSignal:
        await self._assert_candidate_owned(candidate_id, user_id)
        signal = await self.signal_repo.get_for_candidate(signal_id, candidate_id)
        if signal is None:
            raise NotFoundError("Recruiter signal not found")
        return signal

    async def list_signals(
        self,
        candidate_id: UUID,
        user_id: UUID,
        *,
        status: RecruiterSignalStatus | None = None,
        signal_type: RecruiterSignalType | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RecruiterSignal]:
        await self._assert_candidate_owned(candidate_id, user_id)
        return await self.signal_repo.list_for_candidate(
            candidate_id,
            status=status,
            signal_type=signal_type,
            limit=limit,
            offset=offset,
        )

    async def count_signals(
        self,
        candidate_id: UUID,
        user_id: UUID,
        *,
        status: RecruiterSignalStatus | None = None,
        signal_type: RecruiterSignalType | None = None,
    ) -> int:
        await self._assert_candidate_owned(candidate_id, user_id)
        return await self.signal_repo.count_for_candidate(
            candidate_id, status=status, signal_type=signal_type
        )

    @staticmethod
    def _validate_coherence(
        signal_type: RecruiterSignalType, contact: RecruiterContact | None
    ) -> None:
        if signal_type is RecruiterSignalType.RECRUITER_ROLE_RELEVANT and contact is not None:
            raise ValidationError(
                "RECRUITER_ROLE_RELEVANT cannot reference a specific recruiter"
            )
        if signal_type is RecruiterSignalType.RECRUITER_CONTACT_AVAILABLE and contact is None:
            raise ValidationError(
                "RECRUITER_CONTACT_AVAILABLE requires a recruiter contact"
            )
        if signal_type is RecruiterSignalType.RECRUITER_OUTREACH_CANDIDATE and contact is None:
            raise ValidationError(
                "RECRUITER_OUTREACH_CANDIDATE requires a recruiter contact"
            )
