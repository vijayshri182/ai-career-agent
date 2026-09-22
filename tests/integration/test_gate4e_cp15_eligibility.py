"""CP15 controlled matching eligibility + read-only evaluation tests.

Real integration is used throughout (no mocks/spies hiding behavior):
the actual CP14 acceptance fixture is ingested through the CP13 boundary, then
the CP15 eligibility boundary and the read-only evaluator run against the real
persisted state. The read-only path invokes the existing JobMatchScorer /
JobTextParser and must NEVER write a JobMatch, Notification, Job, or candidate
row, and must leave matching.py byte-identical.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.gate4e_ingestion import Gate4eIngestion
from backend.models.job import Job
from backend.models.job_match import JobMatch
from backend.models.notification import Notification
from backend.repositories.candidate import CandidateRepository
from backend.repositories.company import CompanyRepository
from backend.repositories.experience import ExperienceRepository
from backend.repositories.gate4e_ingestion import Gate4eIngestionRepository
from backend.repositories.job import JobRepository
from backend.repositories.job_source import JobSourceRepository
from backend.repositories.skill import SkillRepository
from backend.schemas.gate4e import Gate4eIngressEnvelope
from backend.schemas.gate4e_eligibility import (
    Gate4eEligibilityReason,
)
from backend.services.gate4e_cp10_adapter import Gate4eCp10Adapter
from backend.services.gate4e_eligibility import Gate4eEligibilityService
from backend.services.gate4e_match_evaluation import Gate4eReadOnlyMatchEvaluator

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "gate4e_cp10_official_postings.json"
CP15_FILES = [
    REPO_ROOT / "src" / "backend" / "schemas" / "gate4e_eligibility.py",
    REPO_ROOT / "src" / "backend" / "services" / "gate4e_eligibility.py",
    REPO_ROOT / "src" / "backend" / "services" / "gate4e_match_evaluation.py",
]
MATCHER_SHA256 = "7CBAF15627C44D57EBD7B49AB1D99479BA96A491D70B42002B16AD0C4CF3BB41"
FIXED_GENERATED_AT = "2026-09-20T00:00:00+00:00"
ADAPTER = Gate4eCp10Adapter()
_ALLOWED_MATCHING_IMPORTS = {
    "JobMatchScorer",
    "JobTextParser",
    "CandidateProfile",
    "CandidateSkillProfile",
    "CandidateExperienceProfile",
}
_NETWORK_TOKENS = (
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
    "scrape",
)


async def _ingestion_service(session: AsyncSession):
    from backend.services.gate4e_ingestion import Gate4eIngestionService

    return Gate4eIngestionService(
        candidate_repo=CandidateRepository(session),
        company_repo=CompanyRepository(session),
        job_repo=JobRepository(session),
        ingestion_repo=Gate4eIngestionRepository(session),
        source_repo=JobSourceRepository(session),
    )


async def _eligibility(session: AsyncSession) -> Gate4eEligibilityService:
    return Gate4eEligibilityService(ingestion_repo=Gate4eIngestionRepository(session))


async def _evaluator(session: AsyncSession) -> Gate4eReadOnlyMatchEvaluator:
    return Gate4eReadOnlyMatchEvaluator(
        eligibility=await _eligibility(session),
        candidate_repo=CandidateRepository(session),
        job_repo=JobRepository(session),
        skill_repo=SkillRepository(session),
        experience_repo=ExperienceRepository(session),
    )


async def _ingest_real_fixture(session: AsyncSession, candidate) -> object:
    service = await _ingestion_service(session)
    return await service.ingest_gate4e_envelope(
        candidate.id,
        ADAPTER.load_envelope(FIXTURE_PATH, generated_at=FIXED_GENERATED_AT),
    )


async def _ingest_rows(session: AsyncSession) -> list[Gate4eIngestion]:
    stmt = select(Gate4eIngestion).order_by(Gate4eIngestion.ingestion_identity)
    return list((await session.execute(stmt)).scalars().all())


def _row(*, index: int, verification_status: str | None, **overrides: Any) -> dict[str, Any]:
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
        **overrides,
    }


async def _ingest_extra_records(session: AsyncSession, candidate) -> object:
    """Deterministically create UNRESOLVED and REJECTED_INVALID records."""
    envelope = Gate4eIngressEnvelope(
        schema_version=1,
        producer_id="gate4e",
        producer_version="cp15-test-records",
        generated_at=FIXED_GENERATED_AT,
        rows=[
            _row(index=11, verification_status="UNRESOLVED", company_name="Murky Ltd"),
            _row(index=12, verification_status="BOGUS", company_name="Bad Co"),
            _row(index=13, verification_status=None, company_name="Unknown Co"),
        ],
    )
    service = await _ingestion_service(session)
    return await service.ingest_gate4e_envelope(candidate.id, envelope)


def _stable_eligibility(report) -> list[object]:
    decisions = [
        {
            "alert_index": d.alert_index,
            "gmail_message_id": d.gmail_message_id,
            "ingestion_identity": d.ingestion_identity,
            "posting_key": d.posting_key,
            "job_id": str(d.job_id) if d.job_id else None,
            "verification_status": d.verification_status,
            "processing_status": d.processing_status,
            "eligibility_status": d.eligibility_status.value,
            "eligible_for_matching": d.eligible_for_matching,
            "reason_code": d.reason_code.value,
            "reason_detail": d.reason_detail,
            "missing_required_fields": sorted(d.missing_required_fields),
            "provenance_ref": d.provenance_ref,
        }
        for d in report.decisions
    ]
    decisions.sort(key=lambda d: d["ingestion_identity"] or "")
    return [
        report.policy_version,
        report.partial_with_url_policy,
        report.total_records,
        report.eligible_count,
        report.excluded_count,
        report.matching_invoked_count,
        report.matching_not_invoked_count,
        dict(sorted(report.reason_counts.items())),
        decisions,
    ]


async def _ingestion_count(session: AsyncSession) -> int:
    stmt = select(func.count()).select_from(Gate4eIngestion)
    return int((await session.execute(stmt)).scalar_one())


async def _job_match_count(session: AsyncSession, candidate_id: UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(JobMatch)
        .join(Job, JobMatch.job_id == Job.id)
        .where(Job.candidate_id == candidate_id)
    )
    return int((await session.execute(stmt)).scalar_one())


async def _notification_count(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(Notification))).scalar_one())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


# ------------------------------------------------------------------------ #
# 1-3. Real fixture eligibility overview
# ------------------------------------------------------------------------ #


async def test_real_fixture_eligibility_overview(session: AsyncSession, candidate):
    await _ingest_real_fixture(session, candidate)
    report = await (await _eligibility(session)).evaluate_candidate(candidate.id)
    assert report.total_records == 5
    assert report.eligible_count == 1
    assert report.excluded_count == 4
    assert report.matching_invoked_count == 1
    assert report.matching_not_invoked_count == 4


async def test_verified_eligible(session: AsyncSession, candidate):
    await _ingest_real_fixture(session, candidate)
    report = await (await _eligibility(session)).evaluate_candidate(candidate.id)
    capgemini = next(d for d in report.decisions if d.alert_index == 3)
    assert capgemini.eligible_for_matching is True
    assert capgemini.reason_code is Gate4eEligibilityReason.ELIGIBLE_VERIFIED
    assert capgemini.job_id is not None
    assert capgemini.missing_required_fields == []
    assert capgemini.verification_status == "VERIFIED"


async def test_partial_with_url_conservative_default(session: AsyncSession, candidate):
    await _ingest_real_fixture(session, candidate)
    report = await (await _eligibility(session)).evaluate_candidate(candidate.id)
    optum = next(d for d in report.decisions if d.alert_index == 5)
    assert optum.verification_status == "PARTIAL"
    assert optum.eligible_for_matching is False
    assert optum.reason_code is Gate4eEligibilityReason.EXCLUDED_PARTIAL_WITH_URL_POLICY_PENDING


async def test_partial_with_url_controlled_opt_in(session: AsyncSession, candidate):
    await _ingest_real_fixture(session, candidate)
    report = await (await _eligibility(session)).evaluate_candidate(
        candidate.id, allow_partial_with_url=True
    )
    optum = next(d for d in report.decisions if d.alert_index == 5)
    assert optum.eligible_for_matching is True
    assert optum.reason_code is Gate4eEligibilityReason.ELIGIBLE_PARTIAL_WITH_URL_CONTROLLED
    assert optum.verification_status == "PARTIAL"  # never VERIFIED


async def test_partial_without_url_exclusion(session: AsyncSession, candidate):
    await _ingest_real_fixture(session, candidate)
    report = await (await _eligibility(session)).evaluate_candidate(candidate.id)
    url_less = [d for d in report.decisions if d.alert_index in (1, 2, 4)]
    assert len(url_less) == 3
    assert all(not d.eligible_for_matching for d in url_less)
    assert all(
        d.reason_code is Gate4eEligibilityReason.EXCLUDED_PARTIAL_NO_URL_QUARANTINED
        for d in url_less
    )
    assert all(d.job_id is None for d in url_less)


async def test_unresolved_exclusion(session: AsyncSession, candidate):
    await _ingest_extra_records(session, candidate)
    report = await (await _eligibility(session)).evaluate_candidate(candidate.id)
    unresolved = next(d for d in report.decisions if d.alert_index == 11)
    assert not unresolved.eligible_for_matching
    assert unresolved.reason_code is Gate4eEligibilityReason.EXCLUDED_UNRESOLVED_QUARANTINED
    assert unresolved.verification_status == "UNRESOLVED"


async def test_rejected_invalid_exclusion(session: AsyncSession, candidate):
    await _ingest_extra_records(session, candidate)
    report = await (await _eligibility(session)).evaluate_candidate(candidate.id)
    rejected = next(d for d in report.decisions if d.alert_index == 12)
    assert not rejected.eligible_for_matching
    assert rejected.reason_code is Gate4eEligibilityReason.EXCLUDED_REJECTED_INVALID
    assert rejected.reason_detail == "invalid verification_status: BOGUS"


async def test_missing_fields_remain_unknown(session: AsyncSession, candidate):
    await _ingest_extra_records(session, candidate)
    report = await (await _eligibility(session)).evaluate_candidate(candidate.id)
    unknown = next(d for d in report.decisions if d.alert_index == 13)
    assert not unknown.eligible_for_matching
    assert unknown.verification_status is None  # unknown preserved, not invented
    assert unknown.reason_code is Gate4eEligibilityReason.EXCLUDED_REJECTED_INVALID
    assert unknown.reason_detail == "missing verification_status"


# ------------------------------------------------------------------------ #
# 7-8. Determinism and replay
# ------------------------------------------------------------------------ #


async def test_deterministic_eligibility_result(session: AsyncSession, candidate):
    await _ingest_real_fixture(session, candidate)
    service = await _eligibility(session)
    first = await service.evaluate_candidate(candidate.id)
    second = await service.evaluate_candidate(candidate.id)
    assert _stable_eligibility(first) == _stable_eligibility(second)


async def test_eligibility_replay_after_reingest(session: AsyncSession, candidate):
    service = await _eligibility(session)
    ingestion = await _ingestion_service(session)
    envelope = ADAPTER.load_envelope(FIXTURE_PATH, generated_at=FIXED_GENERATED_AT)
    await ingestion.ingest_gate4e_envelope(candidate.id, envelope)
    before = _stable_eligibility(await service.evaluate_candidate(candidate.id))
    # Replaying the exact same artifact is idempotent; decisions stay stable.
    await ingestion.ingest_gate4e_envelope(candidate.id, envelope)
    after = _stable_eligibility(await service.evaluate_candidate(candidate.id))
    assert before == after
    assert await _ingestion_count(session) == 5


# ------------------------------------------------------------------------ #
# 9-14. Identity preservation and matcher invocation boundary
# ------------------------------------------------------------------------ #


async def test_all_alerts_preserved(session: AsyncSession, candidate):
    await _ingest_real_fixture(session, candidate)
    report = await (await _eligibility(session)).evaluate_candidate(candidate.id)
    assert {d.alert_index for d in report.decisions} == {1, 2, 3, 4, 5}
    gmail_ids = {d.gmail_message_id for d in report.decisions}
    assert len(gmail_ids) == 5


async def test_posting_identity_preserved(session: AsyncSession, candidate):
    await _ingest_real_fixture(session, candidate)
    report = await (await _eligibility(session)).evaluate_candidate(candidate.id)
    evolute = sorted(
        (d for d in report.decisions if d.alert_index in (1, 4)),
        key=lambda d: d.alert_index or 0,
    )
    assert len(evolute) == 2
    assert evolute[0].ingestion_identity != evolute[1].ingestion_identity
    assert evolute[0].posting_key == evolute[1].posting_key


async def test_matcher_invoked_only_for_eligible(session: AsyncSession, candidate):
    await _ingest_real_fixture(session, candidate)
    evaluator = await _evaluator(session)
    report = await evaluator.evaluate_candidate(candidate.id)
    assert report.evaluated_job_count == 1
    assert len(report.outcomes) == 1
    outcome = report.outcomes[0]
    assert outcome.rules_version == "3.0.0"
    decision = next(
        d
        for d in report.eligibility.decisions
        if d.reason_code is Gate4eEligibilityReason.ELIGIBLE_VERIFIED
    )
    assert outcome.job_id == decision.job_id


async def test_matcher_not_invoked_for_quarantined(session: AsyncSession, candidate):
    await _ingest_real_fixture(session, candidate)
    evaluator = await _evaluator(session)
    report = await evaluator.evaluate_candidate(candidate.id)
    evaluated_jobs = {o.job_id for o in report.outcomes}
    # Every evaluated job must correspond to a policy-ELIGIBLE decision.
    eligible_jobs = {d.job_id for d in report.eligibility.decisions if d.eligible_for_matching}
    assert evaluated_jobs <= eligible_jobs
    # No quarantined or excluded record is ever evaluated.
    assert all(
        not d.eligible_for_matching
        for d in report.eligibility.decisions
        if d.alert_index in (1, 2, 4)
    )


async def test_matcher_not_invoked_for_url_less_partial(session: AsyncSession, candidate):
    await _ingest_real_fixture(session, candidate)
    evaluator = await _evaluator(session)
    report = await evaluator.evaluate_candidate(candidate.id)
    assert len(report.outcomes) == 1  # only Capgemini (VERIFIED)
    for decision in report.eligibility.decisions:
        if decision.alert_index in (1, 2, 4):
            assert decision.ingestion_identity not in {
                o.ingestion_identity for o in report.outcomes
            }


# ------------------------------------------------------------------------ #
# 15. No matching algorithm duplication
# ------------------------------------------------------------------------ #


def test_no_matching_algorithm_duplication():
    import ast

    for path in CP15_FILES:
        if path.suffix != ".py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.ImportFrom) and node.module == "backend.services.matching"
            ):
                continue
            names = {alias.name for alias in node.names}
            assert names <= _ALLOWED_MATCHING_IMPORTS, (
                f"{path.name} imported matching internals: {names}"
            )
    # The eligibility/evaluation services must not define scoring constants.
    for path in (CP15_FILES[1], CP15_FILES[2]):
        source = path.read_text(encoding="utf-8")
        for forbidden in ("RULES_VERSION =", "ScoreWeights", "threshold: float = 70", "weights ="):
            assert forbidden not in source, f"{path.name} duplicates matching policy: {forbidden}"
        # Parser/scorer must only come from matching.py (no local reimplementation).
        assert "class JobMatchScorer" not in source
        assert "class JobTextParser" not in source


# ------------------------------------------------------------------------ #
# 16-18. No network / no Gmail/LinkedIn / no outreach
# ------------------------------------------------------------------------ #


@pytest.mark.parametrize("token", _NETWORK_TOKENS)
def test_no_network_surface(token: str):
    for path in CP15_FILES:
        assert token.lower() not in path.read_text(encoding="utf-8").lower(), (
            f"{path.name} contains {token!r}"
        )


@pytest.mark.parametrize(
    "import_fragment", ["outreach", "applications", "automation", "recruiter", "conduct"]
)
def test_no_forbidden_subject_imports(import_fragment: str):
    for path in CP15_FILES:
        assert import_fragment not in path.read_text(encoding="utf-8").lower(), (
            f"{path.name} references {import_fragment!r}"
        )


# ------------------------------------------------------------------------ #
# 19. No unintended database writes
# ------------------------------------------------------------------------ #


async def test_no_unintended_database_writes(session: AsyncSession, candidate):
    await _ingest_real_fixture(session, candidate)
    baseline = (
        await _ingestion_count(session),
        await _job_match_count(session, candidate.id),
        await _notification_count(session),
        await JobRepository(session).count_for_candidate(candidate.id),
    )
    evaluator = await _evaluator(session)
    await evaluator.evaluate_candidate(candidate.id)
    await (await _eligibility(session)).evaluate_candidate(candidate.id)
    after = (
        await _ingestion_count(session),
        await _job_match_count(session, candidate.id),
        await _notification_count(session),
        await JobRepository(session).count_for_candidate(candidate.id),
    )
    assert after == baseline
    assert await _job_match_count(session, candidate.id) == 0
    assert await _notification_count(session) == 0


# ------------------------------------------------------------------------ #
# 20. Matcher stays byte-identical
# ------------------------------------------------------------------------ #


def test_matcher_sha256_unchanged():
    assert _sha256(REPO_ROOT / "src" / "backend" / "services" / "matching.py") == MATCHER_SHA256
