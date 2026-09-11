"""Integration tests for job discovery API and core pipeline."""

from __future__ import annotations

import httpx
from fastapi import Depends
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_session
from backend.app.main import app
from backend.core.config import get_settings
from backend.models.job_source import JobSource
from backend.repositories.agent_task import AgentTaskRepository
from backend.repositories.audit import AuditRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.company import CompanyRepository
from backend.repositories.job import JobRepository
from backend.repositories.job_source import JobSourceRepository
from backend.repositories.raw_job_extraction import RawJobExtractionRepository
from backend.services.adapters.base import AdapterFetchResult, JobSourceAdapter
from backend.services.discovery import DiscoveryService
from backend.services.normalization import JobNormalizer, NormalizedJob


class _StubAdapter:
    """In-memory adapter returning pre-configured postings (no HTTP)."""

    def __init__(self, postings: list[NormalizedJob]) -> None:
        self._postings = postings

    async def fetch(self, source: JobSource) -> AdapterFetchResult:  # noqa: ARG002
        return AdapterFetchResult(
            fetch_url=source.base_url,
            jobs=list(self._postings),
            raw_payload={"stub": True},
        )


def _mock_client_factory() -> httpx.AsyncClient:
    def _handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(_handler), base_url="http://test")


def _build_discovery_service_override(postings: list[NormalizedJob]):
    """Return a FastAPI dependency override that yields a stub-backed DiscoveryService."""

    normalizer = JobNormalizer()

    def _get_service(session: AsyncSession = Depends(get_session)) -> DiscoveryService:
        settings = get_settings()
        def adapter_factory(client: httpx.AsyncClient) -> JobSourceAdapter:
            return _StubAdapter(postings)

        return DiscoveryService(
            candidate_repo=CandidateRepository(session),
            source_repo=JobSourceRepository(session),
            company_repo=CompanyRepository(session),
            job_repo=JobRepository(session),
            extraction_repo=RawJobExtractionRepository(session),
            task_repo=AgentTaskRepository(session),
            audit_repo=AuditRepository(session),
            adapter_factory=adapter_factory,
            client_factory=_mock_client_factory,
            normalizer=normalizer,
            settings=settings,
        )

    return _get_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_source(client: AsyncClient, candidate_id: str, auth_headers: dict) -> dict:
    resp = await client.post(
        f"/api/v1/candidates/{candidate_id}/job-sources",
        json={
            "name": "Test Source",
            "base_url": "https://careers.test",
            "source_type": "job_board",
            "terms_allow_automation": True,
            "crawl_config": {"mode": "html"},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()


async def _enable_source(client: AsyncClient, candidate_id: str, source: dict, auth_headers: dict) -> None:
    resp = await client.put(
        f"/api/v1/candidates/{candidate_id}/job-sources/{source['id']}",
        json={"is_enabled": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_enabled"] is True


async def _run_discovery(client: AsyncClient, candidate_id: str, auth_headers: dict, body: dict | None = None) -> dict:
    resp = await client.post(
        f"/api/v1/candidates/{candidate_id}/discovery-runs",
        json=body or {},
        headers=auth_headers,
    )
    return resp.json()


async def _list_jobs(client: AsyncClient, candidate_id: str, auth_headers: dict) -> list[dict]:
    resp = await client.get(f"/api/v1/candidates/{candidate_id}/jobs", headers=auth_headers)
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_sources_crud(client: AsyncClient, candidate, auth_headers) -> None:
    cid = str(candidate.id)
    source = await _create_source(client, cid, auth_headers)
    assert source["name"] == "Test Source"
    assert source["terms_allow_automation"] is True
    assert source["is_enabled"] is False

    sources_resp = await client.get(f"/api/v1/candidates/{cid}/job-sources", headers=auth_headers)
    assert sources_resp.status_code == 200
    assert len(sources_resp.json()) == 1

    update_resp = await client.put(
        f"/api/v1/candidates/{cid}/job-sources/{source['id']}",
        json={"is_enabled": True},
        headers=auth_headers,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["is_enabled"] is True

    del_resp = await client.delete(
        f"/api/v1/candidates/{cid}/job-sources/{source['id']}",
        headers=auth_headers,
    )
    assert del_resp.status_code == 204


async def test_sources_reject_unsafe_urls(client: AsyncClient, candidate, auth_headers) -> None:
    cid = str(candidate.id)
    for bad_url in ["ftp://example.com", "https://127.0.0.1/jobs"]:
        resp = await client.post(
            f"/api/v1/candidates/{cid}/job-sources",
            json={"base_url": bad_url},
            headers=auth_headers,
        )
        assert resp.status_code == 400, f"Expected 400 for {bad_url}"


async def test_discovery_run_creates_jobs(client: AsyncClient, candidate, auth_headers) -> None:
    cid = str(candidate.id)
    source = await _create_source(client, cid, auth_headers)
    await _enable_source(client, cid, source, auth_headers)

    postings = [
        NormalizedJob(
            title="Software Engineer",
            url="https://careers.test/jobs/1",
            company_name="Acme Inc",
            company_domain="acme.com",
            location="Remote",
            external_id="1",
            content_hash="abc123",
        )
    ]

    from backend.api.deps import get_discovery_service
    app.dependency_overrides[get_discovery_service] = _build_discovery_service_override(postings)

    result = await _run_discovery(client, cid, auth_headers)
    assert "task" in result
    assert result["sources_attempted"] == 1
    assert result["sources_succeeded"] == 1
    assert result["new_jobs"] == 1

    jobs = await _list_jobs(client, cid, auth_headers)
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Software Engineer"

    app.dependency_overrides.clear()


async def test_discovery_run_idempotent(client: AsyncClient, candidate, auth_headers) -> None:
    cid = str(candidate.id)
    source = await _create_source(client, cid, auth_headers)
    await _enable_source(client, cid, source, auth_headers)

    postings = [
        NormalizedJob(
            title="SRE",
            url="https://careers.test/jobs/42",
            company_name="Acme Inc",
            company_domain="acme.com",
            external_id="42",
            content_hash="def456",
        )
    ]

    from backend.api.deps import get_discovery_service
    app.dependency_overrides[get_discovery_service] = _build_discovery_service_override(postings)

    first = await _run_discovery(client, cid, auth_headers)
    assert first["new_jobs"] == 1
    assert first["duplicate_jobs"] == 0

    second = await _run_discovery(client, cid, auth_headers)
    assert second["new_jobs"] == 0
    assert second["duplicate_jobs"] == 1

    jobs = await _list_jobs(client, cid, auth_headers)
    assert len(jobs) == 1

    app.dependency_overrides.clear()


async def test_list_discovery_runs(client: AsyncClient, candidate, auth_headers) -> None:
    cid = str(candidate.id)
    source = await _create_source(client, cid, auth_headers)
    await _enable_source(client, cid, source, auth_headers)

    from backend.api.deps import get_discovery_service
    app.dependency_overrides[get_discovery_service] = _build_discovery_service_override([])

    await _run_discovery(client, cid, auth_headers)
    resp = await client.get(f"/api/v1/candidates/{cid}/discovery-runs", headers=auth_headers)
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) >= 1
    assert runs[0]["task_type"] == "job_discovery"

    app.dependency_overrides.clear()
