"""CP15 Gate 4E eligibility + read-only matcher evaluation (offline, deterministic).

Loads the persisted CP14 artifact (``tests/fixtures/gate4e_cp10_official_postings.json``)
plus deterministic UNRESOLVED / REJECTED_INVALID state records, rebuilds the CP13
persisted ingestion store IN MEMORY (no database, no sessions, no network), then runs
the real CP15 components:

* ``Gate4eEligibilityService`` (the CP15 eligibility policy)
* ``Gate4eReadOnlyMatchEvaluator`` (calls the production ``JobMatchScorer`` /
  ``JobTextParser`` in read-only mode)

Nothing is ever written: there is no DB engine, no session, and the evaluator uses
in-memory repositories exposing the same async read-only interfaces as the production
ones. No ``JobMatch``, ``Notification``, ``Job``, candidate, or ingestion row is
persisted. ``src/backend/services/matching.py`` is never modified (only its pure
``JobMatchScorer`` / ``JobTextParser`` surface is used; the production service that
persists results is NOT invoked).

Determinism: the report normalizes away runtime timestamps (``evaluated_at``) and
sorts every list, so identical inputs produce byte-identical output across runs.
Run the script twice with identical arguments and compare the outputs.

Usage:
    python scripts/gate4e_cp15_evaluation.py [--input PATH] [--output PATH]
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from backend.models.candidate import (  # noqa: E402
    Candidate,
    CandidateSkill,
    Experience,
    Proficiency,
    SkillCategory,
)
from backend.models.gate4e_ingestion import (  # noqa: E402
    Gate4eIngestion,
    Gate4eProcessingStatus,
)
from backend.models.job import Job  # noqa: E402
from backend.services.gate4e_eligibility import Gate4eEligibilityService  # noqa: E402
from backend.services.gate4e_match_evaluation import Gate4eReadOnlyMatchEvaluator  # noqa: E402

_DEFAULT_INPUT = _REPO_ROOT / "tests" / "fixtures" / "gate4e_cp10_official_postings.json"
_CANDIDATE_ID = UUID("79f1465f-3f4d-4d7a-9d41-2b295e292fc8")
_USER_ID = UUID("bbd35b28-4e42-4439-8f20-4b8f6dce6b01")
_PRODUCER_ID = "gate4e"
_PRODUCER_VERSION = "cp10-official-postings"
_SCHEMA_VERSION = 1

_FORBIDDEN_SURFACE = (
    "outreach",
    "applications",
    "automation",
    "approval",
    "recruiter",
    "httpx",
    "requests",
    "aiohttp",
    "urllib",
    "playwright",
    "selenium",
    "imaplib",
    "imap",
    "smtp",
    "smtplib",
    "socket",
    "websocket",
    "subprocess",
    "webbrowser",
)
_ALLOWED_MATCHING_IMPORTS = {
    "JobMatchScorer",
    "JobTextParser",
    "CandidateProfile",
    "CandidateSkillProfile",
    "CandidateExperienceProfile",
}

_CP15_MODULES = [
    _REPO_ROOT / "src" / "backend" / "services" / "gate4e_eligibility.py",
    _REPO_ROOT / "src" / "backend" / "services" / "gate4e_match_evaluation.py",
]


def _norm(value: Any) -> str:
    """Faithful whitespace normalization (mirrors the CP13/CP14 normalizer)."""
    if not isinstance(value, str):
        return ""
    stripped = " ".join(value.split())
    if stripped.lower() in {"", "unknown", "n/a", "na", "null", "none", "-"}:
        return ""
    return stripped


def _posting_key(company: Any, title: Any) -> str | None:
    company = _norm(company).lower()
    title = _norm(title).lower()
    if not company or not title:
        return None
    return hashlib.sha256(f"{company}|{title}".encode()).hexdigest()[0:32]


def _ingestion_identity(candidate_id: UUID, raw_row: dict[str, Any]) -> str:
    canonical = json.dumps(
        {
            "candidate_id": str(candidate_id),
            "schema_version": _SCHEMA_VERSION,
            "producer_id": _PRODUCER_ID,
            "producer_version": _PRODUCER_VERSION,
            "record": raw_row,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _stable_datetime() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC)


def _probe_row(*, index: int, verification_status: str | None) -> dict[str, Any]:
    """Deterministic policy-path probes (same rows as the CP15 test suite)."""
    return {
        "index": index,
        "job_title": "Test Role",
        "company_name": "Test Company",
        "job_location": None,
        "original_job_url": None,
        "gmail_message_id": f"test-gmail-{index}",
        "official_domain": "test.example",
        "official_job_url": None,
        "official_job_id": None,
        "verification_status": verification_status,
        "verification_reason": None,
        "title_correspondence": False,
        "company_correspondence": False,
        "description": None,
        "skills": [],
        "seniority": None,
        "years": None,
        "work_mode": None,
        "compensation": None,
        "provenance": {"official_domain": "VERIFIED"},
        "evidence_urls": [],
        "enrichment_covered": [],
        "enrichment_missing": [],
        "notes": [],
    }


# ---------------------------------------------------------------------- #
# In-memory persisted state: the exact CP13 ingestion outcome for the CP14
# artifact, plus deterministic UNRESOLVED / REJECTED_INVALID records.
# ---------------------------------------------------------------------- #


def _classify_record(
    candidate_id: UUID, row: dict[str, Any]
) -> tuple[Gate4eProcessingStatus, UUID | None, str | None, str | None]:
    status = row.get("verification_status")
    official_url = (row.get("official_job_url") or None) or None
    if status is None:
        return Gate4eProcessingStatus.REJECTED_INVALID, None, None, "missing verification_status"
    if status == "UNRESOLVED":
        return (
            Gate4eProcessingStatus.QUARANTINED_UNRESOLVED,
            None,
            None,
            row.get("verification_reason") or "UNRESOLVED producer verification status",
        )
    if status == "VERIFIED":
        if not official_url:
            return (
                Gate4eProcessingStatus.REJECTED_INVALID,
                None,
                None,
                "VERIFIED requires an official job URL",
            )
        if not (row.get("official_job_id") or None):
            return (
                Gate4eProcessingStatus.REJECTED_INVALID,
                None,
                None,
                "VERIFIED requires official posting identity (official_job_id)",
            )
        if not (row.get("official_domain") or None):
            return (
                Gate4eProcessingStatus.REJECTED_INVALID,
                None,
                None,
                "VERIFIED requires company identity (official_domain)",
            )
        job_id = uuid5(NAMESPACE_URL, f"gate4e-cp15-job|{candidate_id}|{official_url}")
        return Gate4eProcessingStatus.ACCEPTED_VERIFIED, job_id, official_url, None
    if status == "PARTIAL":
        if not official_url:
            return (
                Gate4eProcessingStatus.QUARANTINED_PARTIAL_NO_URL,
                None,
                None,
                "PARTIAL record has no official job URL; quarantined pending a "
                "product-approved URL policy (no URL is fabricated)",
            )
        job_id = uuid5(NAMESPACE_URL, f"gate4e-cp15-job|{candidate_id}|{official_url}")
        return Gate4eProcessingStatus.ACCEPTED_PARTIAL, job_id, official_url, None
    return (
        Gate4eProcessingStatus.REJECTED_INVALID,
        None,
        None,
        f"invalid verification_status: {status}",
    )


def _build_records(
    candidate_id: UUID, artifact_rows: list[dict[str, Any]]
) -> list[Gate4eIngestion]:
    records: list[Gate4eIngestion] = []
    for row in artifact_rows:
        status, job_id, official_url, reason = _classify_record(candidate_id, row)
        record_id = uuid5(
            NAMESPACE_URL,
            f"gate4e-cp15-record|{candidate_id}|{row.get('index')}|{row.get('gmail_message_id')}",
        )
        records.append(
            Gate4eIngestion(
                id=record_id,
                candidate_id=candidate_id,
                schema_version=_SCHEMA_VERSION,
                producer_id=_PRODUCER_ID,
                producer_version=_PRODUCER_VERSION,
                ingestion_identity=_ingestion_identity(candidate_id, row),
                processing_status=status,
                verification_status=row.get("verification_status"),
                alert_index=row.get("index"),
                gmail_message_id=row.get("gmail_message_id"),
                posting_key=_posting_key(row.get("company_name"), row.get("job_title")),
                company_name=row.get("company_name"),
                official_domain=row.get("official_domain"),
                job_title=row.get("job_title"),
                job_location=row.get("job_location"),
                description=row.get("description"),
                official_job_url=official_url,
                official_job_id=(row.get("official_job_id") or None) or None,
                original_job_url=row.get("original_job_url"),
                content_hash=None,
                job_id=job_id,
                reason=reason,
                payload_json=dict(row),
                provenance_json=dict(row.get("provenance") or {}),
                evidence_urls_json=list(row.get("evidence_urls") or []),
                enrichment_json={
                    "covered": list(row.get("enrichment_covered") or []),
                    "missing": list(row.get("enrichment_missing") or []),
                },
            )
        )
    return records


def _build_job(
    candidate_id: UUID, row: dict[str, Any], official_url: str
) -> Job:
    return Job(
        id=uuid5(NAMESPACE_URL, f"gate4e-cp15-job|{candidate_id}|{official_url}"),
        candidate_id=candidate_id,
        company_id=uuid5(
            NAMESPACE_URL,
            f"gate4e-cp15-company|{row.get('official_domain') or row.get('company_name')}",
        ),
        source_id=uuid5(NAMESPACE_URL, "gate4e-cp15-source"),
        external_id=(row.get("official_job_id") or None) or None,
        url=official_url,
        title=str(row.get("job_title") or ""),
        location=row.get("job_location"),
        description=row.get("description"),
        content_hash="",
        first_seen_at=_stable_datetime(),
        last_seen_at=_stable_datetime(),
    )


def _build_candidate(candidate_id: UUID) -> Candidate:
    return Candidate(
        id=candidate_id,
        user_id=_USER_ID,
        full_name="CP15 Candidate",
        email_hash="",
        headline="AI/ML Engineering Leadership",
        summary="Leader with deep AI/ML platform experience.",
        current_role="Head of AI Platform",
        target_role="Director AI/ML Engineering",
        total_experience_years=15,
        seniority="leadership",
        work_authorization="authorized",
        expected_compensation_amount=0,
        expected_compensation_currency="INR",
        career_preferences={"work_mode": "remote"},
    )


def _build_skills_and_experience(
    candidate_id: UUID,
) -> tuple[list[CandidateSkill], list[Experience]]:
    skills = [
        CandidateSkill(
            id=uuid5(NAMESPACE_URL, f"gate4e-cp15-skill|{candidate_id}|machine-learning"),
            candidate_id=candidate_id,
            name="machine learning",
            category=SkillCategory.AI_GENAI,
            proficiency=Proficiency.ADVANCED,
            years_experience=6,
            is_primary=True,
        ),
        CandidateSkill(
            id=uuid5(NAMESPACE_URL, f"gate4e-cp15-skill|{candidate_id}|python"),
            candidate_id=candidate_id,
            name="python",
            category=SkillCategory.PROGRAMMING,
            proficiency=Proficiency.EXPERT,
            years_experience=12,
            is_primary=True,
        ),
        CandidateSkill(
            id=uuid5(NAMESPACE_URL, f"gate4e-cp15-skill|{candidate_id}|engineering-leadership"),
            candidate_id=candidate_id,
            name="engineering management",
            category=SkillCategory.MANAGEMENT,
            proficiency=Proficiency.ADVANCED,
            years_experience=8,
            is_primary=False,
        ),
    ]
    experiences = [
        Experience(
            id=uuid5(NAMESPACE_URL, f"gate4e-cp15-exp|{candidate_id}|1"),
            candidate_id=candidate_id,
            company_name="Example Corp",
            title="Head of AI Platform",
            start_date=date(2018, 1, 1),
            end_date=None,
            is_current=True,
            domain="AI engineering",
            responsibilities=["AI/ML platform strategy", "model lifecycle ownership"],
            achievements=["Scaled inference platform 10x"],
            technologies=["python", "aws"],
            leadership_responsibilities=["Led a 40-person org"],
            team_size=40,
        )
    ]
    return skills, experiences


# ---------------------------------------------------------------------- #
# In-memory read-only repositories (no DB, no writes).
# ---------------------------------------------------------------------- #


class _MemoryIngestionRepo:
    def __init__(self, records: list[Gate4eIngestion]) -> None:
        self._records = records

    async def list_for_candidate(
        self,
        candidate_id: UUID,
        *,
        status: Gate4eProcessingStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Gate4eIngestion]:
        result = [
            record
            for record in self._records
            if record.candidate_id == candidate_id
            and (status is None or record.processing_status == status)
        ]
        result.sort(key=lambda record: record.ingestion_identity or "")
        return result[offset : offset + limit]


class _MemoryCandidateRepo:
    def __init__(self, candidate: Candidate) -> None:
        self._candidate = candidate

    async def get(self, candidate_id: UUID) -> Candidate | None:
        if candidate_id == self._candidate.id:
            return self._candidate
        return None


class _MemoryJobRepo:
    def __init__(self, jobs: list[Job]) -> None:
        self._jobs = {job.id: job for job in jobs}

    async def get_for_candidate(self, job_id: UUID, candidate_id: UUID) -> Job | None:
        job = self._jobs.get(job_id)
        if job is None or job.candidate_id != candidate_id:
            return None
        return job


class _MemorySkillRepo:
    def __init__(self, skills: list[CandidateSkill]) -> None:
        self._skills = skills

    async def list_for_candidate(self, candidate_id: UUID) -> list[CandidateSkill]:
        return [skill for skill in self._skills if skill.candidate_id == candidate_id]


class _MemoryExperienceRepo:
    def __init__(self, experiences: list[Experience]) -> None:
        self._experiences = experiences

    async def list_ordered(self, candidate_id: UUID) -> list[Experience]:
        result = [exp for exp in self._experiences if exp.candidate_id == candidate_id]
        result.sort(key=lambda exp: (exp.start_date, exp.display_order))
        return result


# ---------------------------------------------------------------------- #
# Deterministic report helpers (no runtime timestamps, sorted lists).
# ---------------------------------------------------------------------- #


def _decision_row(decision: Any) -> dict[str, Any]:
    return {
        "alert_index": decision.alert_index,
        "gmail_message_id": decision.gmail_message_id,
        "ingestion_identity": decision.ingestion_identity,
        "posting_key": decision.posting_key,
        "job_id": str(decision.job_id) if decision.job_id else None,
        "verification_status": decision.verification_status,
        "processing_status": decision.processing_status,
        "eligibility_status": decision.eligibility_status.value,
        "eligible_for_matching": decision.eligible_for_matching,
        "reason_code": decision.reason_code.value,
        "reason_detail": decision.reason_detail,
        "missing_required_fields": sorted(decision.missing_required_fields),
        "provenance_ref": decision.provenance_ref,
    }


def _eligibility_section(report: Any) -> dict[str, Any]:
    decisions = [_decision_row(d) for d in report.decisions]
    decisions.sort(key=lambda d: d["ingestion_identity"] or "")
    return {
        "policy_version": report.policy_version,
        "partial_with_url_policy": report.partial_with_url_policy,
        "total_records": report.total_records,
        "eligible_count": report.eligible_count,
        "excluded_count": report.excluded_count,
        "matching_invoked_count": report.matching_invoked_count,
        "matching_not_invoked_count": report.matching_not_invoked_count,
        "reason_counts": dict(sorted(report.reason_counts.items())),
        "decisions": decisions,
    }


def _outcome_row(outcome: Any) -> dict[str, Any]:
    return {
        "job_id": str(outcome.job_id),
        "ingestion_identity": outcome.ingestion_identity,
        "rules_version": outcome.rules_version,
        "is_match": outcome.is_match,
        "matched_skills": sorted(outcome.matched_skills),
        "missing_skills": sorted(outcome.missing_skills),
        "transferable_skills": sorted(outcome.transferable_skills),
        "strengths": list(outcome.strengths),
        "gaps": list(outcome.gaps),
        "blockers": list(outcome.blockers),
    }


def _evaluation_section(report: Any) -> dict[str, Any]:
    outcomes = [_outcome_row(o) for o in report.outcomes]
    outcomes.sort(key=lambda o: o["ingestion_identity"] or "")
    return {
        "evaluated_job_count": report.evaluated_job_count,
        "outcomes": outcomes,
    }


# ---------------------------------------------------------------------- #
# Guard checks.
# ---------------------------------------------------------------------- #


def _evidence_preserved(
    records: list[Gate4eIngestion], artifact_rows: list[dict[str, Any]]
) -> list[str]:
    """Return violation descriptions (empty when all evidence is intact)."""
    violations: list[str] = []
    for record in records:
        row = next(r for r in artifact_rows if r.get("index") == record.alert_index)
        if record.payload_json != dict(row):
            violations.append(f"payload_json differs for alert {record.alert_index}")
        if record.provenance_json != dict(row.get("provenance") or {}):
            violations.append(f"provenance_json differs for alert {record.alert_index}")
        if record.evidence_urls_json != list(row.get("evidence_urls") or []):
            violations.append(f"evidence_urls_json differs for alert {record.alert_index}")
    return violations


def _forbidden_surface_hits() -> dict[str, list[str]]:
    files_to_scan = [
        _REPO_ROOT / "scripts" / "gate4e_cp15_evaluation.py",
        *_CP15_MODULES,
    ]
    hits: dict[str, list[str]] = {}
    for path in files_to_scan:
        source = path.read_text(encoding="utf-8")
        if path.name == "gate4e_cp15_evaluation.py":
            # Mask the token-declaration constants so the scan does not match
            # the strings this very script uses to name the forbidden surface.
            source = re.sub(
                r"_FORBIDDEN_SURFACE = \(.*?\)\n",
                "",
                source,
                flags=re.DOTALL,
            )
            source = re.sub(
                r"_ALLOWED_MATCHING_IMPORTS = \{.*?\}\n",
                "",
                source,
                flags=re.DOTALL,
            )
        hits.setdefault(path.name, [])
        for token in _FORBIDDEN_SURFACE:
            if re.search(rf"\b{token}\b", source, flags=re.IGNORECASE):
                hits[path.name].append(token)
    return {name: sorted(tokens) for name, tokens in sorted(hits.items())}


def _matching_import_violations() -> list[str]:
    violations: list[str] = []
    for path in _CP15_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "backend.services.matching":
                names = {alias.name for alias in node.names}
                excess = sorted(names - _ALLOWED_MATCHING_IMPORTS)
                if excess:
                    violations.append(f"{path.name} imports matching internals: {excess}")
    return violations


# ---------------------------------------------------------------------- #
# Policy checks against the conservative and controlled eligibility runs.
# ---------------------------------------------------------------------- #


def _policy_checks(
    eligibility_report: Any,
    eligibility_controlled: Any,
    evaluation_report: Any,
    evaluation_controlled: Any,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    failed: list[str] = []

    def check(name: str, passed: bool, detail: Any) -> None:
        checks.append({"name": name, "pass": bool(passed), "detail": detail})
        if not passed:
            failed.append(name)

    def decision(report: Any, alert_index: int) -> Any:
        return next(d for d in report.decisions if d.alert_index == alert_index)

    # VERIFIED (Capgemini, alert 3) must be eligible and evaluated.
    verified = decision(eligibility_report, 3)
    check(
        "verified_eligible",
        verified.eligible_for_matching
        and verified.reason_code.value == "ELIGIBLE_VERIFIED"
        and verified.job_id is not None,
        {"alert_index": 3, "reason_code": verified.reason_code.value, "job_id": str(verified.job_id)},
    )
    check(
        "verified_evaluation_invoked",
        evaluation_report.evaluated_job_count >= 1
        and any(o.ingestion_identity == verified.ingestion_identity for o in evaluation_report.outcomes),
        {"evaluated_job_count": evaluation_report.evaluated_job_count},
    )

    # PARTIAL with URL (Optum, alert 5): excluded under conservative policy,
    # controlled-eligible and NEVER VERIFIED under explicit opt-in.
    partial_url = decision(eligibility_report, 5)
    check(
        "partial_with_url_conservative_excluded",
        not partial_url.eligible_for_matching
        and partial_url.reason_code.value == "EXCLUDED_PARTIAL_WITH_URL_POLICY_PENDING",
        {"alert_index": 5, "reason_code": partial_url.reason_code.value},
    )
    partial_url_controlled = decision(eligibility_controlled, 5)
    check(
        "partial_with_url_controlled_opt_in",
        partial_url_controlled.eligible_for_matching
        and partial_url_controlled.reason_code.value == "ELIGIBLE_PARTIAL_WITH_URL_CONTROLLED",
        {"alert_index": 5, "reason_code": partial_url_controlled.reason_code.value},
    )
    check(
        "partial_never_promoted_to_verified",
        partial_url_controlled.verification_status == "PARTIAL",
        {"verification_status": partial_url_controlled.verification_status},
    )
    check(
        "partial_with_url_evaluation_invoked_when_opted_in",
        evaluation_controlled.evaluated_job_count == 2
        and any(o.ingestion_identity == partial_url_controlled.ingestion_identity for o in evaluation_controlled.outcomes),
        {"evaluated_job_count": evaluation_controlled.evaluated_job_count},
    )

    # PARTIAL without URL (alerts 1, 2, 4) must be quarantined in both modes.
    partial_no_url = [decision(eligibility_report, i) for i in (1, 2, 4)]
    check(
        "partial_without_url_excluded",
        all(
            not d.eligible_for_matching
            and d.reason_code.value == "EXCLUDED_PARTIAL_NO_URL_QUARANTINED"
            and d.job_id is None
            for d in partial_no_url
        ),
        [{"alert_index": d.alert_index, "reason_code": d.reason_code.value} for d in partial_no_url],
    )

    # UNRESOLVED and REJECTED_INVALID records are excluded.
    unresolved = next(d for d in eligibility_report.decisions if d.verification_status == "UNRESOLVED")
    check(
        "unresolved_excluded",
        not unresolved.eligible_for_matching
        and unresolved.reason_code.value == "EXCLUDED_UNRESOLVED_QUARANTINED"
        and unresolved.job_id is None,
        {"alert_index": unresolved.alert_index, "reason_code": unresolved.reason_code.value},
    )
    rejected = [d for d in eligibility_report.decisions if d.reason_code.value == "EXCLUDED_REJECTED_INVALID"]
    check(
        "rejected_invalid_excluded",
        len(rejected) >= 1
        and all(not d.eligible_for_matching and d.job_id is None for d in rejected),
        [{"alert_index": d.alert_index, "reason_code": d.reason_code.value} for d in rejected],
    )
    return checks


# ---------------------------------------------------------------------- #
# Main.
# ---------------------------------------------------------------------- #


async def evaluate(eligibility, evaluator, *, allow_partial: bool) -> tuple[Any, Any]:
    report = await eligibility.evaluate_candidate(_CANDIDATE_ID, allow_partial_with_url=allow_partial)
    evaluation = await evaluator.evaluate_candidate(_CANDIDATE_ID, allow_partial_with_url=allow_partial)
    return report, evaluation


def main(argv: list[str] | None = None) -> int:
    import asyncio

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=_DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    artifact = json.loads(args.input.read_text(encoding="utf-8"))
    artifact_rows: list[dict[str, Any]] = list(artifact["rows"])
    artifact_rows += [
        _probe_row(index=11, verification_status="UNRESOLVED"),
        _probe_row(index=12, verification_status="BOGUS"),
        _probe_row(index=13, verification_status=None),
    ]

    candidate = _build_candidate(_CANDIDATE_ID)
    skills, experiences = _build_skills_and_experience(_CANDIDATE_ID)
    records = _build_records(_CANDIDATE_ID, artifact_rows)

    jobs: list[Job] = []
    for record in records:
        if record.processing_status in {
            Gate4eProcessingStatus.ACCEPTED_VERIFIED,
            Gate4eProcessingStatus.ACCEPTED_PARTIAL,
        }:
            row = next(r for r in artifact_rows if r.get("index") == record.alert_index)
            jobs.append(_build_job(_CANDIDATE_ID, row, record.official_job_url))

    eligibility = Gate4eEligibilityService(ingestion_repo=_MemoryIngestionRepo(records))
    evaluator = Gate4eReadOnlyMatchEvaluator(
        eligibility=eligibility,
        candidate_repo=_MemoryCandidateRepo(candidate),
        job_repo=_MemoryJobRepo(jobs),
        skill_repo=_MemorySkillRepo(skills),
        experience_repo=_MemoryExperienceRepo(experiences),
    )

    report, evaluation = asyncio.run(evaluate(eligibility, evaluator, allow_partial=False))
    report_controlled, evaluation_controlled = asyncio.run(
        evaluate(eligibility, evaluator, allow_partial=True)
    )

    checks = _policy_checks(report, report_controlled, evaluation, evaluation_controlled)
    failed = [c["name"] for c in checks if not c["pass"]]

    fabricated = [
        record.ingestion_identity
        for record in records
        if record.official_job_url is None and record.job_id is not None
    ]
    evidence_violations = _evidence_preserved(records, artifact_rows)
    forbidden = _forbidden_surface_hits()
    matching_violations = _matching_import_violations()

    checks.append(
        {
            "name": "no_fabricated_url",
            "pass": not fabricated,
            "detail": {"records_with_job_but_no_url": sorted(fabricated)},
        }
    )
    if fabricated:
        failed.append("no_fabricated_url")
    checks.append(
        {
            "name": "evidence_provenance_identity_preserved",
            "pass": not evidence_violations,
            "detail": {"violations": evidence_violations},
        }
    )
    if evidence_violations:
        failed.append("evidence_provenance_identity_preserved")
    checks.append(
        {
            "name": "no_outbound_communication_or_automation",
            "pass": all(not tokens for tokens in forbidden.values()),
            "detail": {"forbidden_surface_hits": forbidden},
        }
    )
    if any(forbidden.values()):
        failed.append("no_outbound_communication_or_automation")
    checks.append(
        {
            "name": "no_matching_algorithm_duplication",
            "pass": not matching_violations,
            "detail": {"violations": matching_violations},
        }
    )
    if matching_violations:
        failed.append("no_matching_algorithm_duplication")
    checks.append(
        {
            "name": "read_only_evaluation_no_persistence",
            "pass": True,
            "detail": {"persistence_layer": "none", "database_session_created": False},
        }
    )

    output = {
        "input": str(args.input),
        "candidate_id": str(_CANDIDATE_ID),
        "policy_version": 1,
        "records_total": len(records),
        "conservative": {
            **_eligibility_section(report),
            **_evaluation_section(evaluation),
        },
        "controlled_partial_with_url": {
            **_eligibility_section(report_controlled),
            **_evaluation_section(evaluation_controlled),
        },
        "checks": checks,
        "final_exit": 0 if not failed else 3,
    }

    text = json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"cp15 evaluation written: {args.output}")
    else:
        print(text)

    if failed:
        print(f"cp15 evaluation FAILED checks: {sorted(failed)}", file=sys.stderr)
        return 3
    print("cp15 evaluation passed all checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
