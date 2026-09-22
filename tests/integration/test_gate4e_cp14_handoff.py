"""CP14 real Gate 4E -> ACA handoff validation (cases 1-20).

The acceptance fixture is a byte-identical copy of the persisted Gate 4E CP10
artifact (``tests/fixtures/gate4e_cp10_official_postings.json``); the CP14
adapter translates it into the CP13 versioned envelope and the CP13 ingestion
service classifies/persists it. Everything here is offline and deterministic;
no URL is fetched, no Gmail/LinkedIn is touched, and the matcher is left
byte-identical.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import NotFoundError, ValidationError
from backend.models.gate4e_ingestion import Gate4eIngestion, Gate4eProcessingStatus
from backend.models.job import Job, JobStatus
from backend.models.job_match import JobMatch
from backend.repositories.company import CompanyRepository
from backend.repositories.gate4e_ingestion import Gate4eIngestionRepository
from backend.repositories.job import JobRepository
from backend.schemas.gate4e import Gate4eIngressEnvelope
from backend.services.gate4e_cp10_adapter import Gate4eCp10Adapter

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "gate4e_cp10_official_postings.json"
REAL_ARTIFACT_PATH = Path(
    r"C:\Vijay_GitHub\recruiter-email-poc\output\gate4e-cp10\cp10_official_postings.json"
)
MATCHER_PATH = REPO_ROOT / "src" / "backend" / "services" / "matching.py"
GATE4E_CP14_FILES = [
    REPO_ROOT / "src" / "backend" / "schemas" / "gate4e_cp10.py",
    REPO_ROOT / "src" / "backend" / "services" / "gate4e_cp10_adapter.py",
]
EXPECTED_MATCHER_SHA256 = "7CBAF15627C44D57EBD7B49AB1D99479BA96A491D70B42002B16AD0C4CF3BB41"
FIXED_GENERATED_AT = "2026-09-20T00:00:00+00:00"

_FAKE_URL_TOKENS = {"", "#", "unknown", "n/a", "na", "null", "none", "-"}
_NETWORK_TOKENS = (
    "httpx",
    "requests",
    "aiohttp",
    "urllib",
    "playwright",
    "selenium",
    "imap",
    "imaplib",
    "smtp",
    "smtplib",
    "socket",
    "websocket",
    "subprocess",
    "webbrowser",
)

ADAPTER = Gate4eCp10Adapter()


async def _service(session: AsyncSession):
    from backend.repositories.candidate import CandidateRepository
    from backend.repositories.job_source import JobSourceRepository
    from backend.services.gate4e_ingestion import Gate4eIngestionService

    return Gate4eIngestionService(
        candidate_repo=CandidateRepository(session),
        company_repo=CompanyRepository(session),
        job_repo=JobRepository(session),
        ingestion_repo=Gate4eIngestionRepository(session),
        source_repo=JobSourceRepository(session),
    )


async def _ingestion_rows(session: AsyncSession) -> list[Gate4eIngestion]:
    stmt = select(Gate4eIngestion).order_by(Gate4eIngestion.created_at, Gate4eIngestion.id)
    return list((await session.execute(stmt)).scalars().all())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


# ------------------------------------------------------------------------ #
# 1. Real CP10 JSON loads successfully
# ------------------------------------------------------------------------ #


def test_real_cp10_loads_successfully():
    artifact = ADAPTER.load_artifact(FIXTURE_PATH)
    assert artifact.artifact == "gate4e-cp10-official-postings"
    assert artifact.alerts_evaluated == 5
    assert len(artifact.rows) == 5


def test_fixture_is_byte_identical_to_persisted_artifact():
    if not REAL_ARTIFACT_PATH.exists():
        pytest.skip("persisted CP10 artifact not available in this environment")
    assert _sha256(FIXTURE_PATH) == _sha256(REAL_ARTIFACT_PATH)


# ------------------------------------------------------------------------ #
# 2. Adapter produces a valid CP13 envelope
# ------------------------------------------------------------------------ #


def test_adapter_produces_valid_cp13_envelope():
    envelope = ADAPTER.load_envelope(FIXTURE_PATH, generated_at=FIXED_GENERATED_AT)
    assert isinstance(envelope, Gate4eIngressEnvelope)
    assert envelope.schema_version == 1
    assert envelope.producer_id == "gate4e"
    assert envelope.producer_version == "cp10-official-postings"
    assert envelope.alerts_evaluated == 5
    assert len(envelope.rows) == 5
    assert [row["index"] for row in envelope.rows] == [1, 2, 3, 4, 5]


# ------------------------------------------------------------------------ #
# 3. All five alerts are represented
# ------------------------------------------------------------------------ #


async def test_all_five_alerts_preserved(session: AsyncSession, candidate):
    service = await _service(session)
    result = await service.ingest_gate4e_envelope(
        candidate.id,
        ADAPTER.load_envelope(FIXTURE_PATH, generated_at=FIXED_GENERATED_AT),
    )
    assert result.total_records == 5

    rows = await _ingestion_rows(session)
    assert len(rows) == 5
    gmail_ids = {row.gmail_message_id for row in rows}
    assert gmail_ids == {
        "1a0b4d1722b6fab3",
        "1a0a436ca640b58f",
        "1a0b465688809855",
        "1a0b3f786d86c1f2",
        "1a0af3f0c17c2d3f",
    }


# ------------------------------------------------------------------------ #
# 4./5. Evolute alerts 1 and 4: distinct alerts, shared posting identity
# ------------------------------------------------------------------------ #


async def test_evolute_alerts_keep_separate_identities_and_share_posting(
    session: AsyncSession, candidate
):
    envelope = ADAPTER.load_envelope(FIXTURE_PATH, generated_at=FIXED_GENERATED_AT)
    evolute = [row for row in envelope.rows if row["index"] in (1, 4)]
    assert len(evolute) == 2
    assert evolute[0]["gmail_message_id"] != evolute[1]["gmail_message_id"]

    artifact = ADAPTER.load_artifact(FIXTURE_PATH)
    expected_posting_key = ADAPTER.posting_identity_hint(artifact.rows[0])
    assert expected_posting_key == ADAPTER.posting_identity_hint(artifact.rows[3])

    service = await _service(session)
    await service.ingest_gate4e_envelope(candidate.id, envelope)
    rows = await _ingestion_rows(session)
    evolute_rows = [row for row in rows if row.alert_index in (1, 4)]
    assert len(evolute_rows) == 2
    assert evolute_rows[0].ingestion_identity != evolute_rows[1].ingestion_identity
    assert evolute_rows[0].posting_key == evolute_rows[1].posting_key
    assert evolute_rows[0].posting_key == expected_posting_key


# ------------------------------------------------------------------------ #
# 6. Capgemini VERIFIED stays VERIFIED
# ------------------------------------------------------------------------ #


async def test_capgemini_verified_remains_verified(session: AsyncSession, candidate):
    service = await _service(session)
    envelope = ADAPTER.load_envelope(FIXTURE_PATH, generated_at=FIXED_GENERATED_AT)
    result = await service.ingest_gate4e_envelope(candidate.id, envelope)

    assert result.accepted_verified == 1
    capgemini_outcome = next(o for o in result.outcomes if o.alert_index == 3)
    assert capgemini_outcome.processing_status is Gate4eProcessingStatus.ACCEPTED_VERIFIED
    assert capgemini_outcome.verification_status.value == "VERIFIED"
    assert capgemini_outcome.job_id is not None

    row = next(r for r in await _ingestion_rows(session) if r.alert_index == 3)
    assert row.verification_status == "VERIFIED"
    assert row.official_job_id == "519193"
    job = await JobRepository(session).get_for_candidate(capgemini_outcome.job_id, candidate.id)
    assert job is not None
    assert job.external_id == "519193"
    assert job.url == (
        "https://www.capgemini.com/in-en/jobs/519193-en_GB_SAPBTP/CPRD%20Modernization"
    )
    assert job.status is JobStatus.DISCOVERED  # no automatic promotion


# ------------------------------------------------------------------------ #
# 7. Optum PARTIAL stays PARTIAL
# ------------------------------------------------------------------------ #


async def test_optum_partial_remains_partial(session: AsyncSession, candidate):
    service = await _service(session)
    result = await service.ingest_gate4e_envelope(
        candidate.id,
        ADAPTER.load_envelope(FIXTURE_PATH, generated_at=FIXED_GENERATED_AT),
    )
    assert result.accepted_partial == 1
    optum_outcome = next(o for o in result.outcomes if o.alert_index == 5)
    assert optum_outcome.processing_status is Gate4eProcessingStatus.ACCEPTED_PARTIAL
    assert optum_outcome.verification_status.value == "PARTIAL"
    job = await JobRepository(session).get_for_candidate(optum_outcome.job_id, candidate.id)
    assert job is not None
    assert job.external_id == "2358453"
    assert job.status is JobStatus.DISCOVERED  # PARTIAL is never promoted
    assert job.url == (
        "https://careers.unitedhealthgroup.com/job/schaumburg/"
        "director-ai-ml-engineering-remote/34088/95691241120"
    )


# ------------------------------------------------------------------------ #
# 8./9. Mobileum and the other URL-less PARTIAL records are quarantined
# ------------------------------------------------------------------------ #


async def test_partial_without_url_quarantined(session: AsyncSession, candidate):
    service = await _service(session)
    result = await service.ingest_gate4e_envelope(
        candidate.id,
        ADAPTER.load_envelope(FIXTURE_PATH, generated_at=FIXED_GENERATED_AT),
    )
    assert result.quarantined_partial_no_url == 3

    litmus = {
        1: Gate4eProcessingStatus.QUARANTINED_PARTIAL_NO_URL,
        2: Gate4eProcessingStatus.QUARANTINED_PARTIAL_NO_URL,
        3: Gate4eProcessingStatus.ACCEPTED_VERIFIED,
        4: Gate4eProcessingStatus.QUARANTINED_PARTIAL_NO_URL,
        5: Gate4eProcessingStatus.ACCEPTED_PARTIAL,
    }
    for outcome in result.outcomes:
        assert outcome.processing_status is litmus[outcome.alert_index]

    rows = await _ingestion_rows(session)
    quarantined = [row for row in rows if row.alert_index in (1, 2, 4)]
    assert len(quarantined) == 3
    assert all(row.official_job_url is None for row in quarantined)
    assert all(row.job_id is None for row in quarantined)
    mobileum_row = next(row for row in rows if row.alert_index == 2)
    assert mobileum_row.verification_status == "PARTIAL"


# ------------------------------------------------------------------------ #
# 10. No fake URL is generated
# ------------------------------------------------------------------------ #


async def test_no_fake_url_generated(session: AsyncSession, candidate):
    service = await _service(session)
    await service.ingest_gate4e_envelope(
        candidate.id,
        ADAPTER.load_envelope(FIXTURE_PATH, generated_at=FIXED_GENERATED_AT),
    )
    assert await JobRepository(session).count_for_candidate(candidate.id) == 2
    jobs = await JobRepository(session).list_for_candidate(candidate.id)
    for job in jobs:
        assert job.url not in _FAKE_URL_TOKENS
        assert "linkedin.com" not in job.url
        assert "gmail" not in job.url.lower()
        assert job.url.startswith("https://")


# ------------------------------------------------------------------------ #
# 11. Evidence URLs preserved
# ------------------------------------------------------------------------ #


async def test_evidence_urls_preserved(session: AsyncSession, candidate):
    artifact = ADAPTER.load_artifact(FIXTURE_PATH)
    service = await _service(session)
    await service.ingest_gate4e_envelope(
        candidate.id,
        ADAPTER.load_envelope(FIXTURE_PATH, generated_at=FIXED_GENERATED_AT),
    )
    rows = await _ingestion_rows(session)
    by_index = {row.alert_index: row for row in rows}
    assert by_index[3].evidence_urls_json == artifact.rows[2]["evidence_urls"]
    assert by_index[1].evidence_urls_json == ["https://www.linkedin.com/jobs/view/4468339544"]


# ------------------------------------------------------------------------ #
# 12. Provenance preserved
# ------------------------------------------------------------------------ #


async def test_provenance_preserved(session: AsyncSession, candidate):
    artifact = ADAPTER.load_artifact(FIXTURE_PATH)
    service = await _service(session)
    await service.ingest_gate4e_envelope(
        candidate.id,
        ADAPTER.load_envelope(FIXTURE_PATH, generated_at=FIXED_GENERATED_AT),
    )
    rows = await _ingestion_rows(session)
    by_index = {row.alert_index: row for row in rows}
    assert by_index[1].provenance_json == artifact.rows[0]["provenance"]
    assert by_index[1].provenance_json["official_domain"] == "VERIFIED"
    assert "evolute.in" in by_index[1].provenance_json["identity_evidence"]


# ------------------------------------------------------------------------ #
# 13. Official posting ID preserved
# ------------------------------------------------------------------------ #


async def test_official_job_id_preserved(session: AsyncSession, candidate):
    service = await _service(session)
    await service.ingest_gate4e_envelope(
        candidate.id,
        ADAPTER.load_envelope(FIXTURE_PATH, generated_at=FIXED_GENERATED_AT),
    )
    rows = await _ingestion_rows(session)
    by_index = {row.alert_index: row for row in rows}
    assert by_index[3].official_job_id == "519193"
    assert by_index[5].official_job_id == "2358453"
    assert by_index[1].official_job_id is None  # preserved as unknown


# ------------------------------------------------------------------------ #
# 14. Gmail message identity preserved
# ------------------------------------------------------------------------ #


async def test_gmail_message_identity_preserved(session: AsyncSession, candidate):
    artifact = ADAPTER.load_artifact(FIXTURE_PATH)
    service = await _service(session)
    await service.ingest_gate4e_envelope(
        candidate.id,
        ADAPTER.load_envelope(FIXTURE_PATH, generated_at=FIXED_GENERATED_AT),
    )
    rows = await _ingestion_rows(session)
    by_index = {row.alert_index: row for row in rows}
    for index, artifact_row in enumerate(artifact.rows, start=1):
        assert by_index[index].gmail_message_id == artifact_row["gmail_message_id"]


# ------------------------------------------------------------------------ #
# 15. Replaying the exact artifact is idempotent
# ------------------------------------------------------------------------ #


async def test_replay_is_idempotent(session: AsyncSession, candidate):
    service = await _service(session)
    envelope = ADAPTER.load_envelope(FIXTURE_PATH, generated_at=FIXED_GENERATED_AT)

    first = await service.ingest_gate4e_envelope(candidate.id, envelope)
    second = await service.ingest_gate4e_envelope(candidate.id, envelope)

    assert first.total_records == 5
    assert first.accepted_verified == 1
    assert first.accepted_partial == 1
    assert first.quarantined_partial_no_url == 3
    assert first.quarantined_unresolved == 0
    assert first.rejected_invalid == 0
    assert first.duplicates == 0
    assert first.jobs_created == 2

    assert second.duplicates == 5
    assert second.jobs_created == 0
    assert second.accepted_verified == second.accepted_partial == 0
    assert second.quarantined_partial_no_url == 0
    assert all(o.duplicate for o in second.outcomes)

    # Database state after run 2 equals the state after run 1.
    assert len(await _ingestion_rows(session)) == 5
    assert await JobRepository(session).count_for_candidate(candidate.id) == 2

    # Stable identity: same ingestion identities on replay.
    assert {o.ingestion_identity for o in first.outcomes} == {
        o.ingestion_identity for o in second.outcomes
    }

    # Determinism: same business outcome for both runs.
    business = lambda r: [  # noqa: E731
        (o.alert_index, o.processing_status, o.job_id, o.posting_key, o.reason) for o in r.outcomes
    ]
    assert business(first) == business(second)


# ------------------------------------------------------------------------ #
# 16. Malformed CP10 input is rejected deterministically
# ------------------------------------------------------------------------ #


def test_malformed_input_rejected(tmp_path):
    cases = {
        "not-json": b"this is not json",
        "missing-rows": b'{"artifact": "gate4e-cp10-official-postings", "alerts_evaluated": 1}',
        "rows-not-list": (
            b'{"artifact": "gate4e-cp10-official-postings", "alerts_evaluated": 1, "rows": "x"}'
        ),
        "alerts-mismatch": (
            b'{"artifact": "gate4e-cp10-official-postings", "alerts_evaluated": 2, '
            b'"rows": [{"index": 1}]}'
        ),
    }
    for name, content in cases.items():
        path = tmp_path / f"{name}.json"
        path.write_bytes(content)
        with pytest.raises(ValidationError):
            ADAPTER.load_artifact(path)


def test_unsupported_artifact_rejected(tmp_path):
    path = tmp_path / "other.json"
    path.write_text(
        '{"artifact": "gate4e-other-artifact", "alerts_evaluated": 1, "rows": [{"index": 1}]}',
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="unsupported CP10 artifact"):
        ADAPTER.load_artifact(path)


def test_missing_file_rejected_deterministically(tmp_path):
    with pytest.raises(ValidationError, match="cannot read CP10 artifact"):
        ADAPTER.load_artifact(tmp_path / "does-not-exist.json")


# ------------------------------------------------------------------------ #
# 17. Unsupported/invalid schema is rejected
# ------------------------------------------------------------------------ #


def test_adapter_only_emits_supported_schema_version():
    from backend.schemas.gate4e_cp10 import GATE4E_CP10_SCHEMA_VERSION

    assert GATE4E_CP10_SCHEMA_VERSION == 1


async def test_unsupported_schema_version_rejected_by_service(session: AsyncSession, candidate):
    service = await _service(session)
    envelope = ADAPTER.load_envelope(FIXTURE_PATH, generated_at=FIXED_GENERATED_AT)
    bad = Gate4eIngressEnvelope(
        schema_version=99,
        producer_id="gate4e",
        producer_version="cp10-official-postings",
        generated_at=FIXED_GENERATED_AT,
        rows=envelope.rows,
    )
    result = await service.ingest_gate4e_envelope(candidate.id, bad)
    assert result.rejected is True
    assert result.envelope_reason == "unsupported schema_version: 99"
    assert result.rejected_invalid == 5


# ------------------------------------------------------------------------ #
# 18. External URLs are never fetched; 20. no network dependency
# ------------------------------------------------------------------------ #


def test_cp14_files_contain_no_network_surface():
    for path in GATE4E_CP14_FILES:
        source = path.read_text(encoding="utf-8")
        lowered = source.lower()
        offending = [token for token in _NETWORK_TOKENS if token in lowered]
        assert offending == [], f"{path.name} imports/uses network tokens: {offending}"


async def test_nonexistent_candidate_rejected_before_any_persistence(
    session: AsyncSession,
):
    from backend.repositories.candidate import CandidateRepository
    from backend.repositories.gate4e_ingestion import Gate4eIngestionRepository
    from backend.repositories.job import JobRepository
    from backend.repositories.job_source import JobSourceRepository
    from backend.services.gate4e_ingestion import Gate4eIngestionService

    service = Gate4eIngestionService(
        candidate_repo=CandidateRepository(session),
        company_repo=CompanyRepository(session),
        job_repo=JobRepository(session),
        ingestion_repo=Gate4eIngestionRepository(session),
        source_repo=JobSourceRepository(session),
    )
    with pytest.raises(NotFoundError, match="Candidate not found"):
        await service.ingest_gate4e_envelope(
            uuid4(),
            ADAPTER.load_envelope(FIXTURE_PATH, generated_at=FIXED_GENERATED_AT),
        )
    assert await Gate4eIngestionRepository(session).count_for_candidate(uuid4()) == 0


# ------------------------------------------------------------------------ #
# 19. The matcher is never called by ingestion
# ------------------------------------------------------------------------ #


async def test_matcher_never_called(session: AsyncSession, candidate):
    from backend.services import matching

    service = await _service(session)
    await service.ingest_gate4e_envelope(
        candidate.id,
        ADAPTER.load_envelope(FIXTURE_PATH, generated_at=FIXED_GENERATED_AT),
    )
    assert matching.RULES_VERSION == "3.0.0"
    stmt = (
        select(JobMatch)
        .join(Job, JobMatch.job_id == Job.id)
        .where(Job.candidate_id == candidate.id)
    )
    assert len(list((await session.execute(stmt)).scalars().all())) == 0


# ------------------------------------------------------------------------ #
# Regression: matching.py stays byte-identical during CP14
# ------------------------------------------------------------------------ #


def test_matcher_source_hash_unchanged():
    assert MATCHER_PATH.exists()
    assert _sha256(MATCHER_PATH) == EXPECTED_MATCHER_SHA256
