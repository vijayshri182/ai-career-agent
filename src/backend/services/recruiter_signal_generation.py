"""CP17 offline recruiter-signal generation service.

Consumes the CP14/CP15 domain (Gate 4E records, eligibility, read-only
matching evaluation) and the CP16 ``RecruiterSignal`` foundation, and turns
existing persisted recruiter evidence (``RecruiterContact`` + ``ContactSource``)
into durable signals -- or explicit suppression reasons. The generator never:

* contacts, emails, or drafts anything for recruiters,
* scrapes or fetches any page (LinkedIn, Gmail, HTTP, anything),
* discovers or fabricates recruiter data (names, emails, URLs),
* infers identity from unsupported text,
* ranks or scores recruiters, or predicts recruiter response,
* sets ``APPROVED`` (signals are created in ``DISCOVERED`` only).

Everything is deterministic: signal identities reuse the CP16 identity
function, evidence references are derived from persisted anchors, and the run
id contains no timestamps. Re-running identical inputs produces identical
behavior; persisting through the CP16 recorder is idempotent.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from backend.models.recruiter_contact import ContactType
from backend.models.recruiter_signal import RecruiterSignalType
from backend.repositories.audit import AuditRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.job import JobRepository
from backend.repositories.recruiter_contact import (
    ContactSourceRepository,
    RecruiterContactRepository,
)
from backend.repositories.recruiter_signal import RecruiterSignalRepository
from backend.schemas.recruiter_signal import RecruiterSignalCreate
from backend.schemas.recruiter_signal_generation import (
    RECRUITER_SIGNAL_GENERATION_VERSION,
    FieldProvenance,
    GeneratedSignal,
    RecruiterEvidence,
    RecruiterEvidenceStrength,
    RecruiterSignalGenerationResult,
    RecruiterSignalSuppressionReason,
    SignalSuppression,
)
from backend.services.gate4e_match_evaluation import Gate4eReadOnlyMatchEvaluator
from backend.services.recruiter_signal import RecruiterSignalService

_GENERATOR_SOURCE = "cp17.signal_generator"

# Conservative, explicit recruiting-role vocabulary. A role title must contain
# one of these substrings for ROLE_RELEVANT to be considered; inference from a
# person's name is never used.
_RECRUITING_ROLE_KEYWORDS = (
    "talent acquisition",
    "talent partner",
    "talent lead",
    "talent manager",
    "recruiting",
    "recruiter",
    "sourcer",
    "people operations",
    "hr generalist",
    "head of talent",
)

# Adversarial tokens the CP17 surface must never import reference (checked by
# the CP17 safety tests with an AST scan).
_FORBIDDEN_IMPORTS = (
    "httpx",
    "requests",
    "aiohttp",
    "urllib",
    "socket",
    "ssl",
    "playwright",
    "selenium",
    "smtp",
    "smtplib",
    "imaplib",
    "webbrowser",
    "subprocess",
    "backend.services.outreach",
    "backend.services.recruiter_discovery",
    "backend.models.outreach",
)


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _enum_value(value: object) -> str:
    """Normalize a modeled enum column to its string value when read from DB."""
    if isinstance(value, str):
        return value
    raw = getattr(value, "value", value)
    return str(raw) if raw is not None else ""


def _is_linkedin_url(url: str | None) -> bool:
    """Detect a LinkedIn-style profile URL without any I/O or URL parsing libs."""
    if not url:
        return False
    current = (url.strip() or "").lower()
    if "://" in current:
        current = current.split("://", 1)[1]
    current = current.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    current = current.rstrip(".")
    return bool(current) and "linkedin" in current


def _is_valid_email(value: str | None) -> bool:
    if not value:
        return False
    if value.count("@") != 1:
        return False
    local, _, domain = value.partition("@")
    if not local or not domain or "." not in domain:
        return False
    return " " not in value


class RecruiterSignalGenerationService:
    """Deterministic rule engine over persisted recruiter evidence."""

    def __init__(
        self,
        *,
        evaluator: Gate4eReadOnlyMatchEvaluator,
        job_repo: JobRepository,
        contact_repo: RecruiterContactRepository,
        source_repo: ContactSourceRepository,
        signal_repo: RecruiterSignalRepository,
        candidate_repo: CandidateRepository,
        recorder: RecruiterSignalService,
        audit_repo: AuditRepository,
    ) -> None:
        self._evaluator = evaluator
        self._job_repo = job_repo
        self._contact_repo = contact_repo
        self._source_repo = source_repo
        self._signal_repo = signal_repo
        self._candidate_repo = candidate_repo
        self._recorder = recorder
        self._audit_repo = audit_repo

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def generate_for_candidate(
        self,
        candidate_id: UUID,
        user_id: UUID,
        *,
        allow_partial_with_url: bool = False,
    ) -> RecruiterSignalGenerationResult:
        """Generate (or deduplicate) signals for one candidate.

        The CP15 read-only evaluator is the single eligibility + matching source
        (it internally runs the CP15 eligibility service); no eligibility or
        matching rule is re-implemented here.
        """
        await self._candidate_repo.get_for_user_or_404(candidate_id, user_id)
        match_report = await self._evaluator.evaluate_candidate(
            candidate_id, allow_partial_with_url=allow_partial_with_url
        )
        eligibility = match_report.eligibility
        outcomes = {str(o.job_id): o for o in match_report.outcomes}

        eligible_job_ids: list[UUID] = []
        for decision in eligibility.decisions:
            if decision.eligible_for_matching and decision.job_id is not None:
                eligible_job_ids.append(decision.job_id)
        eligible_job_ids = sorted(dict.fromkeys(eligible_job_ids), key=str)

        run_id = hashlib.sha256(
            _canonical_json(
                {
                    "generation_version": RECRUITER_SIGNAL_GENERATION_VERSION,
                    "candidate_id": str(candidate_id),
                    "eligible_job_ids": [str(job_id) for job_id in eligible_job_ids],
                }
            ).encode("utf-8")
        ).hexdigest()

        generated: list[GeneratedSignal] = []
        suppressed: list[SignalSuppression] = []

        # Explicit, auditable suppression for every ineligible decision.
        for decision in eligibility.decisions:
            if decision.eligible_for_matching:
                continue
            reason = (
                RecruiterSignalSuppressionReason.JOB_NOT_ELIGIBLE
                if decision.job_id is not None
                else RecruiterSignalSuppressionReason.CANDIDATE_NOT_ELIGIBLE
            )
            suppressed.append(
                SignalSuppression(
                    reason=reason,
                    reason_detail=decision.reason_detail,
                    job_id=decision.job_id,
                    rule="eligibility_gate",
                    eligibility_code=decision.reason_code.value,
                )
            )

        evidence_loaded: list[RecruiterEvidence] = []
        for job_id in eligible_job_ids:
            job = await self._job_repo.get_for_candidate(job_id, candidate_id)
            if job is None:
                continue
            outcome = outcomes.get(str(job_id))
            match_decision = next(
                (
                    d
                    for d in eligibility.decisions
                    if d.eligible_for_matching and d.job_id == job_id
                ),
                None,
            )
            eligibility_code = (
                match_decision.reason_code.value if match_decision is not None else None
            )

            contacts = await self._contact_repo.list_for_candidate(
                candidate_id,
                company_id=job.company_id,
                surfaced_only=True,
            )
            contacts.sort(key=lambda c: c.public_profile_url or "")

            if not contacts:
                suppressed.append(
                    SignalSuppression(
                        reason=RecruiterSignalSuppressionReason.NO_RECRUITER_EVIDENCE,
                        reason_detail=(
                            "no surfaced recruiter evidence is persisted for this job/company"
                        ),
                        job_id=job.id,
                        rule="evidence_gate",
                        eligibility_code=eligibility_code,
                    )
                )
                continue

            for contact in contacts:
                evidence = await self._extract_evidence(
                    candidate_id, job.id, job.company_id, contact
                )
                evidence_loaded.append(evidence)
                ctx: dict[str, object] = {
                    "candidate_id": candidate_id,
                    "user_id": user_id,
                    "job_id": job.id,
                    "recruiter_id": contact.id,
                    "eligibility_code": eligibility_code,
                    "policy_version": eligibility.policy_version,
                    "evidence": evidence,
                    "outcome": outcome,
                    "generated": generated,
                    "suppressed": suppressed,
                }
                await self._apply_rules(ctx)

        if not generated:
            await self._record_candidate_suppression(
                user_id=user_id, candidate_id=candidate_id, suppressed=suppressed
            )

        result = RecruiterSignalGenerationResult(
            candidate_id=candidate_id,
            run_id=run_id,
            generated_at=datetime.now(UTC),
            policy_version=eligibility.policy_version,
            partial_with_url_policy=eligibility.partial_with_url_policy,
            eligibility_records_total=eligibility.total_records,
            eligible_job_count=len(eligible_job_ids),
            excluded_job_count=eligibility.excluded_count,
            evidence_loaded=evidence_loaded,
            generated=generated,
            suppressed=suppressed,
            created_count=sum(1 for g in generated if g.outcome == "created"),
            deduplicated_count=sum(1 for g in generated if g.outcome == "deduplicated"),
            suppressed_count=len(suppressed),
        )
        result.signal_type_counts = self._count_signal_types(generated)

        await self._audit_repo.log(
            event_type="RECRUITER_SIGNAL_GENERATION_RUN",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="RecruiterSignal",
            metadata={
                "generation_version": RECRUITER_SIGNAL_GENERATION_VERSION,
                "run_id": run_id,
                "eligible_jobs": result.eligible_job_count,
                "excluded_jobs": result.excluded_job_count,
                "created": result.created_count,
                "deduplicated": result.deduplicated_count,
                "suppressed": result.suppressed_count,
            },
        )
        return result

    # ------------------------------------------------------------------ #
    # Evidence extraction (persisted data only; never scraped)
    # ------------------------------------------------------------------ #

    async def _extract_evidence(
        self,
        candidate_id: UUID,
        job_id: UUID,
        company_id: UUID | None,
        contact: object,
    ) -> RecruiterEvidence:
        from backend.models.recruiter_contact import RecruiterContact

        assert isinstance(contact, RecruiterContact)
        source = await self._source_repo.get(contact.source_id)

        fields_provenance: dict[str, FieldProvenance] = {
            field: FieldProvenance(
                field_name=field,
                present=bool(getattr(contact, field, None)),
                source="persisted_recruiter_contact",
                source_reference=str(contact.id),
            )
            for field in ("full_name", "role_title", "public_profile_url", "email")
        }

        evidence_reference = hashlib.sha256(
            _canonical_json(
                {
                    "candidate_id": str(candidate_id),
                    "job_id": str(job_id),
                    "recruiter_id": str(contact.id),
                    "source_id": str(source.id) if source is not None else None,
                }
            ).encode("utf-8")
        ).hexdigest()

        if source is None:
            strength = RecruiterEvidenceStrength.INSUFFICIENT
            source_name = ""
            source_ref = None
        elif not (source.url or "").strip():
            strength = RecruiterEvidenceStrength.INSUFFICIENT
            source_name = _enum_value(source.source_type)
            source_ref = None
        else:
            strength = RecruiterEvidenceStrength.SUPPORTED
            source_name = _enum_value(source.source_type)
            source_ref = source.url

        contact_methods: list[str] = []
        if _is_valid_email(contact.email):
            contact_methods.append("email")
        if _is_linkedin_url(contact.public_profile_url):
            contact_methods.append("linkedin")

        identity_supported = (
            strength is RecruiterEvidenceStrength.SUPPORTED
            and contact.contact_type == ContactType.VERIFIED
            and bool((contact.full_name or "").strip())
            and bool((contact.public_profile_url or "").strip())
            and bool((contact.role_title or "").strip())
        )

        supported_fields = sorted(
            field for field, fp in fields_provenance.items() if fp.present
        )

        return RecruiterEvidence(
            recruiter_id=contact.id,
            candidate_id=candidate_id,
            company_id=company_id,
            job_id=job_id,
            full_name=contact.full_name,
            role_title=contact.role_title,
            public_profile_url=contact.public_profile_url,
            email=contact.email,
            supported_fields=supported_fields,
            contact_methods=contact_methods,
            evidence_strength=strength,
            identity_supported=identity_supported,
            source=source_name,
            source_reference=source_ref,
            evidence_reference=evidence_reference,
            fields_provenance=fields_provenance,
        )

    # ------------------------------------------------------------------ #
    # Rule engine
    # ------------------------------------------------------------------ #

    async def _apply_rules(self, ctx: dict[str, object]) -> None:
        evidence = ctx["evidence"]
        assert isinstance(evidence, RecruiterEvidence)
        recruiter_id = ctx["recruiter_id"]
        assert isinstance(recruiter_id, UUID)

        role_title = (evidence.role_title or "").strip().lower()
        role_relevant = any(kw in role_title for kw in _RECRUITING_ROLE_KEYWORDS)

        if evidence.evidence_strength is not RecruiterEvidenceStrength.SUPPORTED:
            reason = (
                RecruiterSignalSuppressionReason.MISSING_PROVENANCE
                if not evidence.source
                else RecruiterSignalSuppressionReason.UNRESOLVED_SOURCE
            )
            await self._record_suppression(
                ctx, reason, RecruiterSignalType.RECRUITER_ASSOCIATED.value
            )
            if role_relevant:
                await self._record_suppression(
                    ctx, reason, RecruiterSignalType.RECRUITER_ROLE_RELEVANT.value
                )
            await self._record_suppression(
                ctx, reason, RecruiterSignalType.RECRUITER_CONTACT_AVAILABLE.value
            )
            await self._record_suppression(
                ctx, reason, RecruiterSignalType.RECRUITER_OUTREACH_CANDIDATE.value
            )
            return

        # Rule 1: RECRUITER_ASSOCIATED -- explicit, persisted association.
        if evidence.identity_supported:
            await self._generate(
                ctx, RecruiterSignalType.RECRUITER_ASSOCIATED, recruiter_id
            )
        else:
            await self._record_suppression(
                ctx,
                RecruiterSignalSuppressionReason.INSUFFICIENT_RECRUITER_IDENTITY,
                RecruiterSignalType.RECRUITER_ASSOCIATED.value,
            )

        # Rule 2: RECRUITER_ROLE_RELEVANT -- explicit recruiting role without a
        # sufficiently supported person identity (never from a name alone).
        if role_relevant and not evidence.identity_supported:
            await self._generate(ctx, RecruiterSignalType.RECRUITER_ROLE_RELEVANT, None)

        # Rule 3: RECRUITER_CONTACT_AVAILABLE -- a supported public contact
        # method already exists in persisted evidence (never discovered).
        if not evidence.identity_supported:
            await self._record_suppression(
                ctx,
                RecruiterSignalSuppressionReason.INSUFFICIENT_RECRUITER_IDENTITY,
                RecruiterSignalType.RECRUITER_CONTACT_AVAILABLE.value,
            )
        elif not evidence.contact_methods:
            await self._record_suppression(
                ctx,
                RecruiterSignalSuppressionReason.NO_SUPPORTED_CONTACT,
                RecruiterSignalType.RECRUITER_CONTACT_AVAILABLE.value,
            )
        else:
            await self._generate(
                ctx, RecruiterSignalType.RECRUITER_CONTACT_AVAILABLE, recruiter_id
            )

        # Rule 4: RECRUITER_OUTREACH_CANDIDATE -- every required condition holds
        # (eligible job, persisted recruiter evidence, supported identity,
        # provenance). Carries no authorization and takes no action.
        if evidence.identity_supported:
            await self._generate(
                ctx, RecruiterSignalType.RECRUITER_OUTREACH_CANDIDATE, recruiter_id
            )
        else:
            await self._record_suppression(
                ctx,
                RecruiterSignalSuppressionReason.INSUFFICIENT_RECRUITER_IDENTITY,
                RecruiterSignalType.RECRUITER_OUTREACH_CANDIDATE.value,
            )

    async def _generate(
        self,
        ctx: dict[str, object],
        signal_type: RecruiterSignalType,
        recruiter_id: UUID | None,
    ) -> None:
        candidate_id = ctx["candidate_id"]
        assert isinstance(candidate_id, UUID)
        user_id = ctx["user_id"]
        assert isinstance(user_id, UUID)
        job_id = ctx["job_id"]
        assert isinstance(job_id, UUID)
        evidence = ctx["evidence"]
        assert isinstance(evidence, RecruiterEvidence)
        outcome = ctx.get("outcome")
        eligibility_code = ctx.get("eligibility_code")

        evidence_reference = evidence.evidence_reference
        source_reference = evidence.source_reference or evidence_reference

        identity = RecruiterSignalService._signal_identity(
            candidate_id,
            job_id,
            recruiter_id,
            signal_type,
            _GENERATOR_SOURCE,
            source_reference,
        )

        existing = await self._signal_repo.find_by_identity(candidate_id, identity)
        if existing is not None:
            self._append_generated(
                ctx,
                GeneratedSignal(
                    signal_identity=identity,
                    signal_type=signal_type,
                    job_id=job_id,
                    recruiter_id=recruiter_id,
                    evidence_reference=evidence_reference,
                    outcome="deduplicated",
                ),
            )
            await self._record_suppression(
                ctx,
                RecruiterSignalSuppressionReason.DUPLICATE_SIGNAL,
                signal_type.value,
            )
            return

        provenance = {
            "generation_version": RECRUITER_SIGNAL_GENERATION_VERSION,
            "generation_source": _GENERATOR_SOURCE,
            "evidence_reference": evidence_reference,
            "eligibility": {
                "policy_version": ctx.get("policy_version"),
                "reason_code": eligibility_code,
                "match_evaluated": outcome is not None,
            },
            "matching": {
                "rules_version": _attr(outcome, "rules_version"),
                "is_match": _attr(outcome, "is_match"),
            },
            "recruiter_id": str(recruiter_id) if recruiter_id else None,
        }

        signal = await self._recorder.create_signal(
            candidate_id,
            user_id,
            RecruiterSignalCreate(
                job_id=job_id,
                recruiter_contact_id=recruiter_id,
                company_id=evidence.company_id,
                signal_type=signal_type,
                source=_GENERATOR_SOURCE,
                source_reference=source_reference,
                evidence=self._evidence_payload(evidence, signal_type),
                provenance=provenance,
            ),
        )

        self._append_generated(
            ctx,
            GeneratedSignal(
                signal_identity=identity,
                signal_type=signal_type,
                job_id=job_id,
                recruiter_id=recruiter_id,
                evidence_reference=evidence_reference,
                outcome="created",
            ),
        )

        await self._audit_repo.log(
            event_type="RECRUITER_SIGNAL_GENERATED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="RecruiterSignal",
            entity_id=signal.id,
            metadata={
                "generation_version": RECRUITER_SIGNAL_GENERATION_VERSION,
                "rule": signal_type.value,
                "signal_type": signal_type.value,
                "evidence_reference": evidence_reference,
                "recruiter_id": str(recruiter_id) if recruiter_id else None,
                "outcome": "created",
            },
        )

    async def _record_suppression(
        self,
        ctx: dict[str, object],
        reason: RecruiterSignalSuppressionReason,
        rule: str,
    ) -> None:
        job_id = ctx["job_id"]
        assert isinstance(job_id, UUID)
        recruiter_id = ctx["recruiter_id"]
        assert isinstance(recruiter_id, UUID)
        evidence = ctx["evidence"]
        assert isinstance(evidence, RecruiterEvidence)
        eligibility_code_raw = ctx.get("eligibility_code")
        eligibility_code = eligibility_code_raw if isinstance(eligibility_code_raw, str) else None

        entry = SignalSuppression(
            reason=reason,
            reason_detail=_suppression_detail(reason, evidence),
            job_id=job_id,
            recruiter_id=recruiter_id,
            rule=rule,
            eligibility_code=eligibility_code,
        )

        suppressed = ctx["suppressed"]
        assert isinstance(suppressed, list)
        dedup_key = (
            entry.reason.value,
            str(entry.job_id),
            entry.rule,
            str(entry.recruiter_id or ""),
        )
        for existing_entry in suppressed:
            if not isinstance(existing_entry, SignalSuppression):
                continue
            if (
                existing_entry.reason.value,
                str(existing_entry.job_id),
                existing_entry.rule,
                str(existing_entry.recruiter_id or ""),
            ) == dedup_key:
                return
        suppressed.append(entry)

        candidate_id = ctx["candidate_id"]
        assert isinstance(candidate_id, UUID)
        user_id = ctx["user_id"]
        assert isinstance(user_id, UUID)
        await self._audit_repo.log(
            event_type="RECRUITER_SIGNAL_SUPPRESSED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="RecruiterSignal",
            entity_id=evidence.recruiter_id,
            metadata={
                "generation_version": RECRUITER_SIGNAL_GENERATION_VERSION,
                "rule": entry.rule,
                "reason": entry.reason.value,
                "job_id": str(entry.job_id) if entry.job_id else None,
                "recruiter_id": str(entry.recruiter_id or "") or None,
            },
        )

    async def _record_candidate_suppression(
        self,
        *,
        user_id: UUID,
        candidate_id: UUID,
        suppressed: list[SignalSuppression],
    ) -> None:
        """Record the candidate-level ``NO_RECRUITER_EVIDENCE`` suppression.

        Emitted only when a full generation produced no qualifying recruiter
        signal at all. The suppression is candidate-scoped (``job_id=None``)
        and deterministic: re-running identical inputs produces the same single
        entry.
        """
        entry = SignalSuppression(
            reason=RecruiterSignalSuppressionReason.NO_RECRUITER_EVIDENCE,
            reason_detail=(
                "no qualifying recruiter-signal evidence exists for this candidate"
            ),
            job_id=None,
            recruiter_id=None,
            rule="evidence_candidate_gate",
            eligibility_code=None,
        )
        key = (entry.reason.value, entry.rule, "")
        for existing in suppressed:
            if (
                existing.job_id is None
                and (
                    existing.reason.value,
                    existing.rule,
                    str(existing.recruiter_id or ""),
                )
                == key
            ):
                return
        suppressed.append(entry)
        await self._audit_repo.log(
            event_type="RECRUITER_SIGNAL_SUPPRESSED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="RecruiterSignal",
            entity_id=candidate_id,
            metadata={
                "generation_version": RECRUITER_SIGNAL_GENERATION_VERSION,
                "rule": entry.rule,
                "reason": entry.reason.value,
                "job_id": None,
                "recruiter_id": None,
            },
        )

    def _append_generated(self, ctx: dict[str, object], item: GeneratedSignal) -> None:
        generated = ctx["generated"]
        assert isinstance(generated, list)
        generated.append(item)

    @staticmethod
    def _count_signal_types(generated: list[GeneratedSignal]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in generated:
            counts[item.signal_type.value] = counts.get(item.signal_type.value, 0) + 1
        return counts

    @staticmethod
    def _evidence_payload(
        evidence: RecruiterEvidence, signal_type: RecruiterSignalType
    ) -> dict[str, object]:
        return {
            "rule": signal_type.value,
            "job_id": str(evidence.job_id),
            "company_id": str(evidence.company_id) if evidence.company_id else None,
            "recruiter": {
                "id": str(evidence.recruiter_id),
                "full_name": evidence.full_name,
                "role_title": evidence.role_title,
                "public_profile_url": evidence.public_profile_url,
                "email": evidence.email,
            },
            "supported_fields": sorted(evidence.supported_fields),
            "contact_methods": sorted(evidence.contact_methods),
            "evidence": {
                "source": evidence.source,
                "source_reference": evidence.source_reference,
                "evidence_reference": evidence.evidence_reference,
            },
        }


def _suppression_detail(
    reason: RecruiterSignalSuppressionReason,
    evidence: RecruiterEvidence,
) -> str:
    if reason is RecruiterSignalSuppressionReason.DUPLICATE_SIGNAL:
        return "signal already exists for this evidence identity; reused (no duplication)"
    if reason is RecruiterSignalSuppressionReason.MISSING_PROVENANCE:
        return "contact evidence exists but its provenance (ContactSource) is missing; not authoritative"
    if reason is RecruiterSignalSuppressionReason.UNRESOLVED_SOURCE:
        return "evidence source is unresolved (empty reference); not authoritative"
    if reason is RecruiterSignalSuppressionReason.NO_SUPPORTED_CONTACT:
        return "no supported public contact method (verified email or LinkedIn URL) in persisted evidence"
    if reason is RecruiterSignalSuppressionReason.INSUFFICIENT_RECRUITER_IDENTITY:
        return "recruiter identity is not sufficiently supported by persisted evidence"
    return str(reason.value)


def _attr(obj: object, name: str) -> object:
    return getattr(obj, name, None) if obj is not None else None


__all__ = [
    "RecruiterSignalGenerationService",
    "RECRUITER_SIGNAL_GENERATION_VERSION",
    "_GENERATOR_SOURCE",
    "_RECRUITING_ROLE_KEYWORDS",
    "_FORBIDDEN_IMPORTS",
]
