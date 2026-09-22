"""CP15 eligibility boundary: explicit decisions per ACA Gate 4E record.

Gate 4E owns evidence; ACA owns workflow. This service is the thin, explicit
eligibility gate between the CP13/CP14 ingestion store and any future matching
use. It only READS ``gate4e_ingestion_records``, applies a deterministic policy,
and emits reason codes. It performs no writes, no scoring, no ranking, and no
network I/O.

Policy (conservative by default):
* VERIFIED with complete identity + ACA Job  -> ELIGIBLE (ELIGIBLE_VERIFIED).
* PARTIAL with official URL                  -> EXCLUDED by default pending a
  product decision (EXCLUDED_PARTIAL_WITH_URL_POLICY_PENDING); only promoted to
  controlled eligibility (ELIGIBLE_PARTIAL_WITH_URL_CONTROLLED) when the caller
  explicitly opts in via ``allow_partial_with_url=True``. PARTIAL is never
  treated as VERIFIED.
* PARTIAL without official URL               -> EXCLUDED, remains quarantined.
* UNRESOLVED                                -> EXCLUDED, preserved for review.
* REJECTED_INVALID                          -> EXCLUDED, rejection reason kept.
* missing producer fields                   -> preserved as unknown, never
  treated as negative facts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from backend.models.gate4e_ingestion import Gate4eIngestion, Gate4eProcessingStatus
from backend.repositories.gate4e_ingestion import Gate4eIngestionRepository
from backend.schemas.gate4e_eligibility import (
    GATE4E_ELIGIBILITY_POLICY_VERSION,
    Gate4eEligibilityDecision,
    Gate4eEligibilityReason,
    Gate4eEligibilityReport,
    Gate4eEligibilityStatus,
)

_TRUEY_FIELDS = ("official_job_url", "official_job_id", "official_domain")


class Gate4eEligibilityService:
    """Deterministic, read-only eligibility evaluation for one candidate."""

    def __init__(self, *, ingestion_repo: Gate4eIngestionRepository) -> None:
        self._ingestion_repo = ingestion_repo

    async def evaluate_candidate(
        self, candidate_id: UUID, *, allow_partial_with_url: bool = False
    ) -> Gate4eEligibilityReport:
        records = await self._ingestion_repo.list_for_candidate(candidate_id)
        decisions = [
            self._decide(record, allow_partial_with_url=allow_partial_with_url)
            for record in records
        ]
        decisions.sort(key=lambda d: d.ingestion_identity or "")

        eligible_count = sum(1 for d in decisions if d.eligible_for_matching)
        reason_counts: dict[str, int] = {}
        for decision in decisions:
            reason_counts[decision.reason_code.value] = (
                reason_counts.get(decision.reason_code.value, 0) + 1
            )

        return Gate4eEligibilityReport(
            candidate_id=candidate_id,
            policy_version=GATE4E_ELIGIBILITY_POLICY_VERSION,
            partial_with_url_policy=(
                "controlled_evaluation" if allow_partial_with_url else "excluded_conservative"
            ),
            evaluated_at=datetime.now(UTC),
            total_records=len(decisions),
            eligible_count=eligible_count,
            excluded_count=len(decisions) - eligible_count,
            matching_invoked_count=eligible_count,
            matching_not_invoked_count=len(decisions) - eligible_count,
            reason_counts=reason_counts,
            decisions=decisions,
        )

    def _base_decision(self, record: Gate4eIngestion) -> Gate4eEligibilityDecision:
        return Gate4eEligibilityDecision(
            alert_index=record.alert_index,
            gmail_message_id=record.gmail_message_id,
            ingestion_identity=record.ingestion_identity,
            posting_key=record.posting_key,
            job_id=record.job_id,
            verification_status=record.verification_status,
            processing_status=Gate4eProcessingStatus(record.processing_status).value,
            eligibility_status=Gate4eEligibilityStatus.EXCLUDED,
            eligible_for_matching=False,
            reason_code=Gate4eEligibilityReason.EXCLUDED_UNKNOWN_STATE,
            reason_detail="",
            missing_required_fields=[],
            provenance_ref=self._provenance_ref(record),
        )

    def _decide(
        self, record: Gate4eIngestion, *, allow_partial_with_url: bool
    ) -> Gate4eEligibilityDecision:
        processing = Gate4eProcessingStatus(record.processing_status)
        base = self._base_decision(record)

        if processing is Gate4eProcessingStatus.REJECTED_INVALID:
            return base.model_copy(
                update={
                    "reason_code": Gate4eEligibilityReason.EXCLUDED_REJECTED_INVALID,
                    "reason_detail": record.reason or "record rejected as invalid by ingestion",
                }
            )

        if processing is Gate4eProcessingStatus.QUARANTINED_UNRESOLVED:
            return base.model_copy(
                update={
                    "reason_code": Gate4eEligibilityReason.EXCLUDED_UNRESOLVED_QUARANTINED,
                    "reason_detail": record.reason
                    or "UNRESOLVED producer verification; preserved for review",
                }
            )

        if processing is Gate4eProcessingStatus.QUARANTINED_PARTIAL_NO_URL:
            return base.model_copy(
                update={
                    "reason_code": Gate4eEligibilityReason.EXCLUDED_PARTIAL_NO_URL_QUARANTINED,
                    "reason_detail": (
                        "PARTIAL record without an official URL; quarantined, no URL fabricated"
                    ),
                    "missing_required_fields": self._missing_for(record, ("official_job_url",)),
                }
            )

        if processing is Gate4eProcessingStatus.ACCEPTED_VERIFIED:
            return self._verified_decision(base, record)

        if processing is Gate4eProcessingStatus.ACCEPTED_PARTIAL:
            return self._partial_decision(
                base, record, allow_partial_with_url=allow_partial_with_url
            )

        return base.model_copy(
            update={
                "reason_detail": f"unexpected processing status: {processing.value}",
            }
        )

    def _verified_decision(
        self, base: Gate4eEligibilityDecision, record: Gate4eIngestion
    ) -> Gate4eEligibilityDecision:
        missing = self._missing_for(record, _TRUEY_FIELDS)
        if missing:
            return base.model_copy(
                update={
                    "reason_code": Gate4eEligibilityReason.EXCLUDED_VERIFIED_INCOMPLETE_IDENTITY,
                    "reason_detail": "VERIFIED record missing required identity evidence",
                    "missing_required_fields": missing,
                }
            )
        if record.job_id is None:
            return base.model_copy(
                update={
                    "reason_code": Gate4eEligibilityReason.EXCLUDED_NO_JOB,
                    "reason_detail": "VERIFIED record has no normalized ACA Job",
                }
            )
        return base.model_copy(
            update={
                "eligibility_status": Gate4eEligibilityStatus.ELIGIBLE,
                "eligible_for_matching": True,
                "reason_code": Gate4eEligibilityReason.ELIGIBLE_VERIFIED,
                "reason_detail": (
                    "VERIFIED with complete identity and ACA Job; controlled matching "
                    "evaluation permitted"
                ),
            }
        )

    def _partial_decision(
        self,
        base: Gate4eEligibilityDecision,
        record: Gate4eIngestion,
        *,
        allow_partial_with_url: bool,
    ) -> Gate4eEligibilityDecision:
        if not record.official_job_url or not str(record.official_job_url).strip():
            return base.model_copy(
                update={
                    "reason_code": Gate4eEligibilityReason.EXCLUDED_PARTIAL_NO_URL_QUARANTINED,
                    "reason_detail": (
                        "PARTIAL record without an official URL; quarantined, no URL fabricated"
                    ),
                    "missing_required_fields": self._missing_for(record, ("official_job_url",)),
                }
            )
        if record.job_id is None:
            return base.model_copy(
                update={
                    "reason_code": Gate4eEligibilityReason.EXCLUDED_NO_JOB,
                    "reason_detail": "PARTIAL-with-URL record has no normalized ACA Job",
                }
            )
        if not allow_partial_with_url:
            return base.model_copy(
                update={
                    "reason_code": Gate4eEligibilityReason.EXCLUDED_PARTIAL_WITH_URL_POLICY_PENDING,
                    "reason_detail": (
                        "PARTIAL-with-official-URL exclusion under conservative policy; "
                        "product decision on PARTIAL matching eligibility required"
                    ),
                }
            )
        return base.model_copy(
            update={
                "eligibility_status": Gate4eEligibilityStatus.ELIGIBLE,
                "eligible_for_matching": True,
                "reason_code": Gate4eEligibilityReason.ELIGIBLE_PARTIAL_WITH_URL_CONTROLLED,
                "reason_detail": (
                    "PARTIAL-with-official-URL controlled evaluation under explicit "
                    "policy opt-in; remains PARTIAL, never VERIFIED"
                ),
            }
        )

    @staticmethod
    def _missing_for(record: Gate4eIngestion, fields: tuple[str, ...]) -> list[str]:
        values = {
            "official_job_url": record.official_job_url,
            "official_job_id": record.official_job_id,
            "official_domain": record.official_domain,
            "job_id": str(record.job_id) if record.job_id is not None else None,
        }
        return [field for field in fields if not values[field]]

    @staticmethod
    def _provenance_ref(record: Gate4eIngestion) -> str:
        return (
            f"gate4e/{record.producer_version}/schema{record.schema_version};"
            f"identity={record.ingestion_identity}"
        )
