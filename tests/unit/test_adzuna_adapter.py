"""Tests for the Adzuna job-search API adapter and mode routing."""

from __future__ import annotations

from uuid import uuid4

import httpx

from backend.models.job_source import JobSource, JobSourceType
from backend.services.adapters.adzuna import AdzunaAdapter
from backend.services.adapters.dispatch import RoutingAdapter
from backend.services.normalization import JobNormalizer

_SAMPLE_PAYLOAD = {
    "count": 2,
    "total": 2,
    "results": [
        {
            "id": "abc123",
            "title": "Senior Python Engineer",
            "redirect_url": "https://www.adzuna.co.uk/jobs/details/abc123",
            "company": {"display_name": "Example Ltd", "url": "https://www.example.com"},
            "location": {"display_name": "London"},
            "description": "Deep Python knowledge required.",
            "created": "2026-09-01T08:30:00.000Z",
            "salary_min": 80000,
            "salary_max": 100000,
        },
        {
            "id": 456,
            "title": "DevOps Engineer",
            "redirect_url": "",
            "company": {"display_name": "ACME"},
            "location": {"display_name": "Remote"},
            "description": "Terraform and AWS.",
            "created": "2026-09-02T09:00:00.000Z",
        },
    ],
}


def _source(**config) -> JobSource:
    return JobSource(
        candidate_id=uuid4(),
        name="Adzuna",
        base_url="https://adzuna.com",
        source_type=JobSourceType.API,
        terms_allow_automation=True,
        is_enabled=True,
        crawl_config={"mode": "adzuna", **config},
    )


def _adapter(
    handler, *, app_id: str | None = "test-app", app_key: str | None = "test-key"
) -> AdzunaAdapter:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.adzuna.com")
    return AdzunaAdapter(
        client,
        JobNormalizer(),
        app_id=app_id,
        app_key=app_key,
        user_agent="AI-Career-Agent/0.1 (test)",
        timeout=5.0,
    )


async def test_fetch_maps_adzuna_payload() -> None:
    seen: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        seen["params"] = dict(request.url.params)
        seen["path"] = request.url.path
        return httpx.Response(200, json=_SAMPLE_PAYLOAD)

    adapter = _adapter(handler)
    result = await adapter.fetch(_source())

    params = seen["params"]
    assert params.get("app_id") == "test-app"
    assert params.get("app_key") == "test-key"
    assert params.get("content-type") == "application/json"
    assert params.get("results_per_page") == "50"
    assert seen["path"] == "/v1/api/jobs/gb/search/1/"

    assert result.error is None
    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.title == "Senior Python Engineer"
    assert job.url == "https://www.adzuna.co.uk/jobs/details/abc123"
    assert job.external_id == "abc123"
    assert job.company_name == "Example Ltd"
    assert job.company_domain == "example.com"
    assert job.location == "London"
    assert job.posted_at is not None
    assert job.posted_at.year == 2026
    assert job.posted_at.tzinfo is not None
    assert len(job.content_hash) == 64
    assert result.raw_payload == {"count": 2, "total": 2}


async def test_fetch_without_credentials_makes_no_request() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        raise AssertionError("network must not be touched without credentials")

    adapter = _adapter(handler, app_id=None, app_key=None)
    result = await adapter.fetch(_source())
    assert result.jobs == []
    assert result.error
    assert "not configured" in result.error


async def test_fetch_invalid_country_rejected() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        raise AssertionError("network must not be touched for an invalid country")

    adapter = _adapter(handler)
    result = await adapter.fetch(_source(country="not-a-country"))
    assert result.jobs == []
    assert result.error
    assert "country" in result.error


async def test_fetch_honors_configurable_country_and_terms() -> None:
    seen: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        seen["path"] = request.url.path
        return httpx.Response(200, json={"results": []})

    adapter = _adapter(handler)
    await adapter.fetch(_source(country="us", what="backend", results_per_page=10))
    assert seen["path"] == "/v1/api/jobs/us/search/1/"
    assert seen["params"].get("results_per_page") == "10"
    assert seen["params"].get("what") == "backend"


async def test_fetch_filters_result_without_url() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(200, json=_SAMPLE_PAYLOAD)

    adapter = _adapter(handler)
    result = await adapter.fetch(_source())
    urls = [job.url for job in result.jobs]
    assert "https://www.adzuna.co.uk/jobs/details/abc123" in urls
    assert all(url for url in urls)


async def test_routing_adapter_dispatches_by_mode() -> None:
    calls: list[str] = []

    class _Recorder:
        def __init__(self, name: str) -> None:
            self.name = name

        async def fetch(self, source):  # noqa: ANN001
            calls.append(self.name)
            from backend.services.adapters.base import AdapterFetchResult

            return AdapterFetchResult(fetch_url=source.base_url)

    router = RoutingAdapter(default=_Recorder("default"), specialized={"adzuna": _Recorder("adzuna")})
    await router.fetch(_source())
    await router.fetch(_source(mode="json"))
    assert calls == ["adzuna", "default"]
