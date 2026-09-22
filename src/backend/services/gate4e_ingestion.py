"""ACA-owned ingestion boundary for the versioned Gate 4E evidence envelope.

Consumes a CP12 Option-B envelope (read-only, no network), validates it,
classifies each per-alert record, and persists a lossless ACA-owned record
(`gate4e_ingestion_records`). The boundary never:

* fabricates or substitutes a URL (URL-less PARTIAL is quarantined),
* promotes PARTIAL/UNRESOLVED to VERIFIED,
* interprets missing enrichment fields as negative facts,
* automatically promotes an ACA ``Job`` to ``VERIFIED`` (G4E VERIFIED enters as
  ``DISCOVERED`` pending an explicit approval gate),
* calls or modifies the matching engine, or
* performs any network I/O.

Verification semantics are exact per the CP12 contract mapping: VERIFIED requires
company + posting identity + an official job URL; PARTIAL is accepted only as the
ACA ``DISCOVERED`` lifecycle; PARTIAL without an official URL and UNRESOLVED are
quarantined rather than forced into the NOT-NULL ``Job.url`` column.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import ValidationError as PydanticValidationError

from backend.core.exceptions import NotFoundError, ValidationError
from backend.models.gate4e_ingestion import Gate4eProcessingStatus
from backend.models.job import Job, JobStatus
from backend.models.job_source import JobSource, JobSourceType
from backend.repositories.candidate import CandidateRepository
from backend.repositories.company import CompanyRepository
from backend.repositories.gate4e_ingestion import Gate4eIngestionRepository
from backend.repositories.job import JobRepository
from backend.repositories.job_source import JobSourceRepository
from backend.schemas.gate4e import (
    SUPPORTED_GATE4E_SCHEMA_VERSIONS,
    Gate4eIngestionOutcome,
    Gate4eIngestionResult,
    Gate4eIngressEnvelope,
    Gate4eIngressRecord,
    Gate4eVerificationStatus,
)
from backend.services.normalization import JobNormalizer
from backend.services.url_validation import validate_source_url

_GATE4E_SOURCE_NAME = "gate4e-handoff"
_GATE4E_SOURCE_BASE_URL = "https://gate4e.invalid/handoff"
_GATE4E_VERIFICATION_VALUES = {v.value for v in Gate4eVerificationStatus}


class Gate4eIngestionService:
    """Classify and persist one Gate 4E envelope for one candidate."""

    def __init__(
        self,
        *,
        candidate_repo: CandidateRepository,
        company_repo: CompanyRepository,
        job_repo: JobRepository,
        ingestion_repo: Gate4eIngestionRepository,
        source_repo: JobSourceRepository,
        normalizer: JobNormalizer | None = None,
    ) -> None:
        self._candidate_repo = candidate_repo
        self._company_repo = company_repo
        self._job_repo = job_repo
        self._ingestion_repo = ingestion_repo
        self._source_repo = source_repo
        self._normalizer = normalizer or JobNormalizer()

    async def ingest_gate4e_envelope(
        self, candidate_id: UUID, envelope: Gate4eIngressEnvelope
    ) -> Gate4eIngestionResult:
        """Validate the envelope and deterministically ingest every record."""
        candidate = await self._candidate_repo.get(candidate_id)
        if candidate is None:
            raise NotFoundError("Candidate not found")

        rejected, envelope_reason = self._validate_envelope(envelope)

        result = Gate4eIngestionResult(
            candidate_id=candidate_id,
            schema_version=envelope.schema_version,
            producer_id=envelope.producer_id,
            producer_version=envelope.producer_version,
            generated_at=envelope.generated_at,
            rejected=rejected,
            envelope_reason=envelope_reason,
            total_records=len(envelope.rows),
        )

        for row in envelope.rows:
            if rejected:
                outcome = _rejected_outcome(row, reason=envelope_reason or "invalid envelope")
            else:
                outcome = await self._process_row(candidate_id, envelope, row)
            result.outcomes.append(outcome)
            self._accumulate(result, outcome)

        return result

    # ------------------------------------------------------------------ #
    # Envelope / record validation
    # ------------------------------------------------------------------ #

    def _validate_envelope(self, envelope: Gate4eIngressEnvelope) -> tuple[bool, str | None]:
        if envelope.schema_version is None:
            return True, "missing schema_version"
        if envelope.schema_version not in SUPPORTED_GATE4E_SCHEMA_VERSIONS:
            return True, f"unsupported schema_version: {envelope.schema_version}"
        if not envelope.producer_id:
            return True, "missing producer_id"
        if not envelope.producer_version:
            return True, "missing producer_version"
        if not envelope.generated_at:
            return True, "missing generated_at"
        return False, None

    async def _process_row(
        self,
        candidate_id: UUID,
        envelope: Gate4eIngressEnvelope,
        raw_row: dict[str, Any],
    ) -> Gate4eIngestionOutcome:
        ingestion_identity = self._ingestion_identity(candidate_id, envelope, raw_row)
        existing = await self._ingestion_repo.find_by_identity(candidate_id, ingestion_identity)
        if existing is not None:
            return Gate4eIngestionOutcome(
                alert_index=existing.alert_index,
                verification_status=_verification_enum(existing.verification_status),
                processing_status=Gate4eProcessingStatus(existing.processing_status),
                ingestion_identity=ingestion_identity,
                posting_key=existing.posting_key,
                job_id=existing.job_id,
                reason=existing.reason,
                duplicate=True,
            )

        raw_status = raw_row.get("verification_status")
        if raw_status is None or raw_status not in _GATE4E_VERIFICATION_VALUES:
            reason = (
                "missing verification_status"
                if raw_status is None
                else f"invalid verification_status: {raw_status}"
            )
            await self._persist_raw_rejected(
                candidate_id, envelope, raw_row, ingestion_identity, reason
            )
            return _rejected_outcome(raw_row, reason=reason, identity=ingestion_identity)

        try:
            record = Gate4eIngressRecord.model_validate(raw_row)
        except PydanticValidationError as exc:
            reason = f"malformed record: {exc.errors()[0]['msg']}"
            await self._persist_raw_rejected(
                candidate_id, envelope, raw_row, ingestion_identity, reason
            )
            return _rejected_outcome(raw_row, reason=reason, identity=ingestion_identity)

        if not str(record.job_title or "").strip():
            reason = "missing job_title"
            await self._persist_raw_rejected(
                candidate_id, envelope, raw_row, ingestion_identity, reason
            )
            return _rejected_outcome(raw_row, reason=reason, identity=ingestion_identity)
        if not str(record.company_name or "").strip():
            reason = "missing company_name"
            await self._persist_raw_rejected(
                candidate_id, envelope, raw_row, ingestion_identity, reason
            )
            return _rejected_outcome(raw_row, reason=reason, identity=ingestion_identity)

        disposition, job_id, job_created, classify_reason = await self._classify(
            candidate_id, envelope, record
        )
        posting_key = self._posting_key(record)

        await self._persist(
            candidate_id,
            envelope,
            record,
            raw_row,
            ingestion_identity,
            disposition,
            job_id,
            posting_key,
            classify_reason,
        )
        return Gate4eIngestionOutcome(
            alert_index=record.index,
            verification_status=record.verification_status,
            processing_status=disposition,
            ingestion_identity=ingestion_identity,
            posting_key=posting_key,
            job_id=job_id,
            reason=classify_reason,
            job_created=job_created,
        )

    # ------------------------------------------------------------------ #
    # Classification
    # ------------------------------------------------------------------ #

    async def _classify(
        self,
        candidate_id: UUID,
        envelope: Gate4eIngressEnvelope,
        record: Gate4eIngressRecord,
    ) -> tuple[Gate4eProcessingStatus, UUID | None, bool, str | None]:
        status = record.verification_status
        if status is None:
            return (
                Gate4eProcessingStatus.REJECTED_INVALID,
                None,
                False,
                "missing verification_status",
            )
        official_url = self._validated_official_url(record)
        if official_url is False:
            return (
                Gate4eProcessingStatus.REJECTED_INVALID,
                None,
                False,
                "invalid official_job_url",
            )

        status_meta = self._verification_meta(status)

        if status is Gate4eVerificationStatus.VERIFIED:
            if official_url is None:
                return (
                    Gate4eProcessingStatus.REJECTED_INVALID,
                    None,
                    False,
                    "VERIFIED requires an official job URL",
                )
            if not record.official_job_id:
                return (
                    Gate4eProcessingStatus.REJECTED_INVALID,
                    None,
                    False,
                    "VERIFIED requires official posting identity (official_job_id)",
                )
            if not record.official_domain:
                return (
                    Gate4eProcessingStatus.REJECTED_INVALID,
                    None,
                    False,
                    "VERIFIED requires company identity (official_domain)",
                )
            job, created = await self._upsert_job(candidate_id, envelope, record, official_url)
            return Gate4eProcessingStatus.ACCEPTED_VERIFIED, job.id, created, status_meta

        if status is Gate4eVerificationStatus.PARTIAL:
            if official_url is None:
                return (
                    Gate4eProcessingStatus.QUARANTINED_PARTIAL_NO_URL,
                    None,
                    False,
                    "PARTIAL record has no official job URL; quarantined pending a "
                    "product-approved URL policy (no URL is fabricated)",
                )
            job, created = await self._upsert_job(candidate_id, envelope, record, official_url)
            return Gate4eProcessingStatus.ACCEPTED_PARTIAL, job.id, created, status_meta

        # UNRESOLVED.
        reason = record.verification_reason or "UNRESOLVED producer verification status"
        return Gate4eProcessingStatus.QUARANTINED_UNRESOLVED, None, False, reason

    def _validated_official_url(self, record: Gate4eIngressRecord) -> str | None | Literal[False]:
        """Return the official URL when valid, None when absent, False when invalid."""
        if not record.official_job_url or not str(record.official_job_url).strip():
            return None
        try:
            return validate_source_url(str(record.official_job_url))
        except ValidationError:
            return False

    def _verification_meta(self, status: Gate4eVerificationStatus) -> str | None:
        return {
            Gate4eVerificationStatus.VERIFIED: "gate4e VERIFIED evidence",
            Gate4eVerificationStatus.PARTIAL: "gate4e PARTIAL evidence (never promoted to VERIFIED)",
        }.get(status)

    # ------------------------------------------------------------------ #
    # ACA-owned Job representation (identity C)
    # ------------------------------------------------------------------ #

    async def _upsert_job(
        self,
        candidate_id: UUID,
        envelope: Gate4eIngressEnvelope,
        record: Gate4eIngressRecord,
        official_url: str,
    ) -> tuple[Job, bool]:
        company = await self._company_repo.get_or_create_by_domain(
            name=str(record.company_name), domain=record.official_domain
        )
        title = self._normalizer.normalize_text(str(record.job_title))
        location = self._normalizer.clean_optional(record.job_location)
        description = self._normalizer.clean_optional(record.description)
        content_hash = self._normalizer.content_hash(title, location, description)

        existing = await self._job_repo.find_identical(
            candidate_id,
            url=official_url,
            company_id=company.id,
            external_id=record.official_job_id,
            content_hash=content_hash,
        )
        if existing is not None:
            return existing, False

        source = await self._gate4e_source(candidate_id)
        job = await self._job_repo.create(
            candidate_id=candidate_id,
            company_id=company.id,
            source_id=source.id,
            external_id=record.official_job_id,
            url=official_url,
            title=title,
            location=location,
            description=description,
            content_hash=content_hash,
            status=JobStatus.DISCOVERED,
            posted_at=None,
            closing_at=None,
            first_seen_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
        )
        return job, True

    async def _gate4e_source(self, candidate_id: UUID) -> JobSource:
        for source in await self._source_repo.list_for_candidate(candidate_id):
            if source.name == _GATE4E_SOURCE_NAME:
                return source
        return await self._source_repo.create(
            candidate_id=candidate_id,
            name=_GATE4E_SOURCE_NAME,
            source_type=JobSourceType.API,
            base_url=_GATE4E_SOURCE_BASE_URL,
            terms_allow_automation=False,
            is_enabled=False,
        )

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    async def _persist(
        self,
        candidate_id: UUID,
        envelope: Gate4eIngressEnvelope,
        record: Gate4eIngressRecord,
        raw_row: dict[str, Any],
        ingestion_identity: str,
        disposition: Gate4eProcessingStatus,
        job_id: UUID | None,
        posting_key: str | None,
        reason: str | None,
    ) -> None:
        await self._ingestion_repo.create(
            candidate_id=candidate_id,
            schema_version=envelope.schema_version or 0,
            producer_id=str(envelope.producer_id),
            producer_version=str(envelope.producer_version),
            ingestion_identity=ingestion_identity,
            processing_status=disposition,
            verification_status=(
                record.verification_status.value if record.verification_status else None
            ),
            alert_index=record.index,
            gmail_message_id=record.gmail_message_id,
            posting_key=posting_key,
            company_name=self._normalizer.clean_optional(record.company_name),
            official_domain=record.official_domain,
            job_title=self._normalizer.normalize_text(str(record.job_title)),
            job_location=self._normalizer.clean_optional(record.job_location),
            description=self._normalizer.clean_optional(record.description),
            official_job_url=record.official_job_url,
            official_job_id=record.official_job_id,
            original_job_url=record.original_job_url,
            content_hash=self._content_hash(record),
            job_id=job_id,
            reason=reason,
            payload_json=self._record_payload(raw_row, record),
            provenance_json=dict(record.provenance),
            evidence_urls_json=list(record.evidence_urls),
            enrichment_json=self._enrichment_json(record),
        )

    async def _persist_raw_rejected(
        self,
        candidate_id: UUID,
        envelope: Gate4eIngressEnvelope,
        raw_row: dict[str, Any],
        ingestion_identity: str,
        reason: str,
    ) -> None:
        await self._ingestion_repo.create(
            candidate_id=candidate_id,
            schema_version=envelope.schema_version or 0,
            producer_id=str(envelope.producer_id),
            producer_version=str(envelope.producer_version),
            ingestion_identity=ingestion_identity,
            processing_status=Gate4eProcessingStatus.REJECTED_INVALID,
            verification_status=None,
            alert_index=_int_or_none(raw_row.get("index")),
            gmail_message_id=_as_optional_str(raw_row.get("gmail_message_id")),
            posting_key=None,
            company_name=self._normalizer.clean_optional(
                _as_optional_str(raw_row.get("company_name"))
            ),
            official_domain=_as_optional_str(raw_row.get("official_domain")),
            job_title=self._normalizer.normalize_text(_as_optional_str(raw_row.get("job_title"))),
            job_location=self._normalizer.clean_optional(
                _as_optional_str(raw_row.get("job_location"))
            ),
            description=self._normalizer.clean_optional(
                _as_optional_str(raw_row.get("description"))
            ),
            official_job_url=_as_optional_str(raw_row.get("official_job_url")),
            official_job_id=_as_optional_str(raw_row.get("official_job_id")),
            original_job_url=_as_optional_str(raw_row.get("original_job_url")),
            content_hash=None,
            job_id=None,
            reason=reason,
            payload_json=dict(raw_row),
            provenance_json=_as_dict(raw_row.get("provenance")),
            evidence_urls_json=_as_str_list(raw_row.get("evidence_urls")),
            enrichment_json={},
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _content_hash(self, record: Gate4eIngressRecord) -> str:
        title = self._normalizer.normalize_text(str(record.job_title))
        location = self._normalizer.clean_optional(record.job_location)
        description = self._normalizer.clean_optional(record.description)
        return self._normalizer.content_hash(title, location, description)

    def _record_payload(
        self, raw_row: dict[str, Any], record: Gate4eIngressRecord
    ) -> dict[str, Any]:
        payload = dict(raw_row)
        payload.update(record.model_dump(mode="json"))
        return payload

    def _enrichment_json(self, record: Gate4eIngressRecord) -> dict[str, Any]:
        return {
            "skills": list(record.skills),
            "seniority": record.seniority,
            "years": record.years,
            "work_mode": record.work_mode,
            "compensation": record.compensation,
            "enrichment_covered": list(record.enrichment_covered),
            "enrichment_missing": list(record.enrichment_missing),
            "notes": list(record.notes),
        }

    def _posting_key(self, record: Gate4eIngressRecord) -> str | None:
        company = self._normalizer.normalize_text(str(record.company_name)).lower()
        title = self._normalizer.normalize_text(str(record.job_title)).lower()
        if not company or not title:
            return None
        return hashlib.sha256(f"{company}|{title}".encode()).hexdigest()[0:32]

    def _ingestion_identity(
        self, candidate_id: UUID, envelope: Gate4eIngressEnvelope, raw_row: dict[str, Any]
    ) -> str:
        canonical = json.dumps(
            {
                "candidate_id": str(candidate_id),
                "schema_version": envelope.schema_version,
                "producer_id": envelope.producer_id,
                "producer_version": envelope.producer_version,
                "record": raw_row,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _accumulate(result: Gate4eIngestionResult, outcome: Gate4eIngestionOutcome) -> None:
        if outcome.duplicate:
            result.duplicates += 1
            return
        if outcome.processing_status is Gate4eProcessingStatus.ACCEPTED_VERIFIED:
            result.accepted_verified += 1
        elif outcome.processing_status is Gate4eProcessingStatus.ACCEPTED_PARTIAL:
            result.accepted_partial += 1
        elif outcome.processing_status is Gate4eProcessingStatus.QUARANTINED_PARTIAL_NO_URL:
            result.quarantined_partial_no_url += 1
        elif outcome.processing_status is Gate4eProcessingStatus.QUARANTINED_UNRESOLVED:
            result.quarantined_unresolved += 1
        else:
            result.rejected_invalid += 1
        if outcome.job_created:
            result.jobs_created += 1


def _rejected_outcome(
    raw_row: dict[str, Any], reason: str, identity: str | None = None
) -> Gate4eIngestionOutcome:
    return Gate4eIngestionOutcome(
        alert_index=_int_or_none(raw_row.get("index")),
        processing_status=Gate4eProcessingStatus.REJECTED_INVALID,
        ingestion_identity=identity,
        reason=reason,
    )


def _verification_enum(value: str | None) -> Gate4eVerificationStatus | None:
    if value is None:
        return None
    try:
        return Gate4eVerificationStatus(value)
    except ValueError:
        return None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    return None


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, str) and value.strip():
        return [value]
    return []
