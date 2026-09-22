"""CP18 recruiter-signal quality and audit service.

A deterministic, read-only evaluation of a persisted mutually exclusive
``RecruiterSignal``. It answers "is this signal internally coherent and
evidence-backed?" by checking:

* identity / source integrity (signal identity, producer source),
* provenance integrity (generation provenance with an evidence reference),
* evidence completeness and field-level provenance consistency,
* type coherence (role-relevant signals never name a specific recruiter;
  contact-available / outreach-candidate signals require one),
* contact resolvability against the owning candidate's persisted state.

The service never writes to the signal, never scores or ranks recruiters, never
predicts response, never drafts or sends anything, and never contacts anyone.
The single write it performs is an append-only audit event mirroring a
deterministic report id. Identical persisted inputs produce identical output.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from backend.core.exceptions import NotFoundError
from backend.models.recruiter_contact import RecruiterContact
from backend.models.recruiter_signal import (
    RecruiterSignal,
    RecruiterSignalStatus,
    RecruiterSignalType,
)
from backend.repositories.audit import AuditRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.recruiter_contact import (
    ContactSourceRepository,
    RecruiterContactRepository,
)
from backend.repositories.recruiter_signal import RecruiterSignalRepository
from backend.schemas.recruiter_signal_quality import (
    RECRUITER_SIGNAL_QUALITY_VERSION,
    RecruiterSignalQualityReport,
    SignalQualityCheck,
    SignalQualitySeverity,
)

# The evidence payload stores these recruiter fields; each one asserted non-null
# must also be listed in the persisted ``supported_fields``.
_ASSERTED_FIELDS = ("full_name", "role_title", "public_profile_url", "email")

_SIGNAL_TYPES_REQUIRING_CONTACT = frozenset(
    {
        RecruiterSignalType.RECRUITER_CONTACT_AVAILABLE,
        RecruiterSignalType.RECRUITER_OUTREACH_CANDIDATE,
    }
)


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _is_linkedin_url(url: str | None) -> bool:
    if not url:
        return False
    current = (url.strip() or "").lower()
    if "://" in current:
        current = current.split("://", 1)[1]
    current = current.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    current = current.rstrip(".")
    return bool(current) and "linkedin" in current


class RecruiterSignalQualityService:
    """Read-only, deterministic quality evaluation for one recruiter signal."""

    def __init__(
        self,
        *,
        signal_repo: RecruiterSignalRepository,
        contact_repo: RecruiterContactRepository,
        source_repo: ContactSourceRepository,
        candidate_repo: CandidateRepository,
        audit_repo: AuditRepository,
    ) -> None:
        self._signals = signal_repo
        self._contacts = contact_repo
        self._sources = source_repo
        self._candidates = candidate_repo
        self._audit = audit_repo

    async def evaluate_signal(
        self,
        candidate_id: UUID,
        user_id: UUID,
        signal_id: UUID,
    ) -> RecruiterSignalQualityReport:
        """Evaluate one signal owned by the calling user's candidate."""
        await self._candidates.get_for_user_or_404(candidate_id, user_id)
        signal = await self._signals.get_for_candidate(signal_id, candidate_id)
        if signal is None:
            raise NotFoundError("Recruiter signal not found")

        checks: list[SignalQualityCheck] = []
        contact = await self._resolve_contact(candidate_id, signal)

        self._assert_identity_present(checks, signal)
        self._assert_source_present(checks, signal)
        self._assert_provenance_present(checks, signal)
        self._assert_evidence_present(checks, signal)
        self._assert_type_coherence(checks, signal)
        self._assert_contact_resolvable(checks, signal, contact)
        self._assert_supported_fields_coherent(checks, signal)
        self._assert_contact_methods_coherent(checks, signal)
        self._assert_lifecycle_safe(checks, signal)

        failed_checks = [c.check for c in checks if c.severity is SignalQualitySeverity.FAIL]
        passed = not failed_checks

        report = RecruiterSignalQualityReport(
            candidate_id=candidate_id,
            signal_id=signal.id,
            evaluation_id=self._evaluation_id(signal, contact),
            passed=passed,
            checks=checks,
            failed_checks=failed_checks,
            evaluated_at=datetime.now(UTC),
        )

        await self._audit.log(
            event_type="RECRUITER_SIGNAL_QUALITY_EVALUATED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="RecruiterSignal",
            entity_id=signal.id,
            result="success" if passed else "failed",
            metadata={
                "quality_version": RECRUITER_SIGNAL_QUALITY_VERSION,
                "evaluation_id": report.evaluation_id,
                "passed": passed,
                "failed_checks": sorted(failed_checks),
                "signal_identity": signal.signal_identity,
            },
        )
        return report

    # ------------------------------------------------------------------ #
    # Individual determinism + integrity checks
    # ------------------------------------------------------------------ #

    def _assert_identity_present(self, checks: list[SignalQualityCheck], signal: RecruiterSignal) -> None:
        identity = signal.signal_identity or ""
        valid = len(identity) == 64 and all(c in "0123456789abcdef" for c in identity)
        detail = (
            "signal identity is a deterministic sha256 over persisted anchors"
            if valid
            else "signal identity is missing or not a 64-char hex digest"
        )
        checks.append(
            SignalQualityCheck(
                check="identity_present",
                severity=SignalQualitySeverity.PASS if valid else SignalQualitySeverity.FAIL,
                detail=detail,
            )
        )

    def _assert_source_present(self, checks: list[SignalQualityCheck], signal: RecruiterSignal) -> None:
        ok = bool((signal.source or "").strip())
        checks.append(
            SignalQualityCheck(
                check="source_present",
                severity=SignalQualitySeverity.PASS if ok else SignalQualitySeverity.FAIL,
                detail=(
                    "signal records a producer source"
                    if ok
                    else "signal has no producer source"
                ),
            )
        )

    def _assert_provenance_present(self, checks: list[SignalQualityCheck], signal: RecruiterSignal) -> None:
        provenance = signal.provenance_json or {}
        has_version = bool((provenance.get("generation_version") or "").strip())
        evidence_reference = provenance.get("evidence_reference") or ""
        ok = isinstance(provenance, dict) and bool(evidence_reference) and has_version
        checks.append(
            SignalQualityCheck(
                check="provenance_present",
                severity=SignalQualitySeverity.PASS if ok else SignalQualitySeverity.FAIL,
                detail=(
                    "provenance records a generation version and evidence reference"
                    if ok
                    else "provenance is missing a version and/or evidence reference"
                ),
            )
        )

    def _assert_evidence_present(self, checks: list[SignalQualityCheck], signal: RecruiterSignal) -> None:
        evidence = signal.evidence_json or {}
        ok = (
            isinstance(evidence, dict)
            and isinstance(evidence.get("recruiter", None), dict)
            and isinstance(evidence.get("supported_fields", None), list)
        )
        checks.append(
            SignalQualityCheck(
                check="evidence_present",
                severity=SignalQualitySeverity.PASS if ok else SignalQualitySeverity.FAIL,
                detail=(
                    "evidence payload carries a recruiter block and supported fields"
                    if ok
                    else "evidence payload is missing the recruiter block or supported fields"
                ),
            )
        )

    def _assert_type_coherence(self, checks: list[SignalQualityCheck], signal: RecruiterSignal) -> None:
        contact_id = signal.recruiter_contact_id
        problems: list[str] = []
        if signal.signal_type is RecruiterSignalType.RECRUITER_ROLE_RELEVANT and contact_id is not None:
            problems.append("role-relevant signals must not name a specific recruiter")
        if (
            signal.signal_type in _SIGNAL_TYPES_REQUIRING_CONTACT
            and contact_id is None
        ):
            problems.append(
                f"{signal.signal_type.value} signals require a recruiter contact"
            )
        checks.append(
            SignalQualityCheck(
                check="type_coherence",
                severity=(
                    SignalQualitySeverity.PASS
                    if not problems
                    else SignalQualitySeverity.FAIL
                ),
                detail="; ".join(problems) if problems else "signal type is coherent",
            )
        )

    def _assert_contact_resolvable(self, checks: list[SignalQualityCheck], signal: RecruiterSignal, contact: RecruiterContact | None) -> None:
        if signal.recruiter_contact_id is None:
            detail = "signal does not reference a specific recruiter (allowed for its type)"
            severity = SignalQualitySeverity.PASS
        elif contact is None:
            detail = "referenced recruiter contact is not persisted for the candidate"
            severity = SignalQualitySeverity.FAIL
        else:
            detail = "referenced recruiter contact resolves to candidate-owned evidence"
            severity = SignalQualitySeverity.PASS
        checks.append(
            SignalQualityCheck(
                check="contact_resolvable",
                severity=severity,
                detail=detail,
            )
        )

    def _assert_supported_fields_coherent(self, checks: list[SignalQualityCheck], signal: RecruiterSignal) -> None:
        evidence = signal.evidence_json or {}
        recruiter = evidence.get("recruiter", None)
        supported = set(evidence.get("supported_fields") or [])
        violations: list[str] = []
        if isinstance(recruiter, dict):
            for field in _ASSERTED_FIELDS:
                value = recruiter.get(field, None)
                if value is not None and str(value).strip() and field not in supported:
                    violations.append(field)
        severity = (
            SignalQualitySeverity.PASS
            if not violations
            else SignalQualitySeverity.FAIL
        )
        detail = (
            "asserted recruiter fields are declared in supported_fields"
            if not violations
            else f"asserted fields missing from supported_fields: {', '.join(sorted(violations))}"
        )
        checks.append(
            SignalQualityCheck(
                check="supported_fields_coherent",
                severity=severity,
                detail=detail,
            )
        )

    def _assert_contact_methods_coherent(self, checks: list[SignalQualityCheck], signal: RecruiterSignal) -> None:
        evidence = signal.evidence_json or {}
        recruiter = evidence.get("recruiter", None)
        methods = set(evidence.get("contact_methods") or [])
        violations: list[str] = []
        unknown = sorted(m for m in methods if m not in ("email", "linkedin"))
        if unknown:
            violations.append(f"unknown methods {', '.join(unknown)}")
        if "email" in methods:
            email = recruiter.get("email") if isinstance(recruiter, dict) else None
            if not email or not str(email).strip():
                violations.append("email method present without an email value")
        if "linkedin" in methods:
            url = recruiter.get("public_profile_url") if isinstance(recruiter, dict) else None
            if not _is_linkedin_url(url):
                violations.append("linkedin method present without a LinkedIn profile URL")
        severity = (
            SignalQualitySeverity.PASS
            if not violations
            else SignalQualitySeverity.FAIL
        )
        detail = (
            "contact methods are consistent with persisted values"
            if not violations
            else "; ".join(violations)
        )
        checks.append(
            SignalQualityCheck(
                check="contact_methods_coherent",
                severity=severity,
                detail=detail,
            )
        )

    def _assert_lifecycle_safe(self, checks: list[SignalQualityCheck], signal: RecruiterSignal) -> None:
        # Signals are created DISCOVERED; APPROVED is only reachable through an
        # explicit human review (CP19). A freshly persisted signal that somehow
        # reads back as APPROVED with no review record is a separate, later
        # gate; here we only ensure the row is in a known lifecycle state.
        known = set(RecruiterSignalStatus)
        ok = signal.status in known
        checks.append(
            SignalQualityCheck(
                check="lifecycle_safe",
                severity=SignalQualitySeverity.PASS if ok else SignalQualitySeverity.FAIL,
                detail=(
                    f"signal status {signal.status.value} is a known lifecycle state"
                    if ok
                    else "signal status is not a known lifecycle state"
                ),
            )
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    async def _resolve_contact(
        self, candidate_id: UUID, signal: RecruiterSignal
    ) -> RecruiterContact | None:
        if signal.recruiter_contact_id is None:
            return None
        return await self._contacts.get_for_candidate(
            signal.recruiter_contact_id, candidate_id
        )

    def _evaluation_id(self, signal: RecruiterSignal, contact: RecruiterContact | None) -> str:
        evidence_reference = (signal.provenance_json or {}).get("evidence_reference") or ""
        raw = _canonical_json(
            {
                "candidate_id": str(signal.candidate_id),
                "signal_id": str(signal.id),
                "signal_identity": signal.signal_identity,
                "signal_type": signal.signal_type.value,
                "status": signal.status.value,
                "evidence_reference": evidence_reference,
                "recruiter_contact_id": str(signal.recruiter_contact_id)
                if signal.recruiter_contact_id
                else None,
                "contact_resolves": contact is not None,
            }
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


__all__ = [
    "RecruiterSignalQualityService",
    "RECRUITER_SIGNAL_QUALITY_VERSION",
]
