"""Adzuna job-search API adapter.

Adds an optional ``mode: "adzuna"`` job source. Adzuna is an authenticated
JSON API: it requires real operator credentials (``ADZUNA_APP_ID`` and
``ADZUNA_APP_KEY``) supplied through the environment. This adapter never
fabricates credentials; when the credentials are absent it reports a clear,
honest configuration error and performs no network I/O. When present they are
sent only to ``api.adzuna.com`` as query parameters and never stored on the
``JobSource`` row or in any database config.

Source ``crawl_config`` offers optional ``country`` (two-letter Adzuna market,
default ``gb``), ``results_per_page`` (capped at 50), and ``what``/``where``
search terms. Adzuna content is untrusted external data and goes through the
same normalization/hash/dedup pipeline as every other source.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from backend.models.job_source import JobSource
from backend.services.adapters.base import AdapterFetchResult
from backend.services.normalization import JobNormalizer, NormalizedJob, domain_of, parse_utc

_DEFAULT_COUNTRY = "gb"
_DEFAULT_RESULTS_PER_PAGE = 50
_MAX_RESULTS_PER_PAGE = 50


def _as_text(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, (str, int, float)):
        return str(value)
    return ""


class AdzunaAdapter:
    """Fetches and normalizes the Adzuna job-search API for one run."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        normalizer: JobNormalizer,
        *,
        app_id: str | None,
        app_key: str | None,
        user_agent: str,
        timeout: float,
    ) -> None:
        self.client = client
        self.normalizer = normalizer
        self.app_id = app_id
        self.app_key = app_key
        self.user_agent = user_agent
        self.timeout = timeout

    async def fetch(self, source: JobSource) -> AdapterFetchResult:
        config = source.crawl_config or {}
        country = str(config.get("country") or _DEFAULT_COUNTRY).lower()
        if not country or not re.fullmatch(r"[a-z]{2}", country):
            return AdapterFetchResult(
                fetch_url=source.base_url,
                error=f"invalid Adzuna country code: {country!r}",
            )

        raw_limit = config.get("results_per_page")
        if raw_limit is None or isinstance(raw_limit, bool):
            limit = _DEFAULT_RESULTS_PER_PAGE
        elif isinstance(raw_limit, (str, int, float)):
            try:
                limit = int(raw_limit)
            except (TypeError, ValueError):
                limit = _DEFAULT_RESULTS_PER_PAGE
        else:
            limit = _DEFAULT_RESULTS_PER_PAGE
        limit = max(1, min(limit, _MAX_RESULTS_PER_PAGE))

        if not self.app_id or not self.app_key:
            return AdapterFetchResult(
                fetch_url=source.base_url,
                error=(
                    "Adzuna API credentials are not configured; set ADZUNA_APP_ID "
                    "and ADZUNA_APP_KEY in the environment"
                ),
            )

        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1/"
        params: dict[str, str | int] = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "results_per_page": limit,
            "content-type": "application/json",
        }
        for term in ("what", "where"):
            value = config.get(term)
            if isinstance(value, str) and value.strip():
                params[term] = value.strip()

        try:
            response = await self.client.get(
                url,
                params=params,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            return AdapterFetchResult(
                fetch_url=url,
                error=f"Adzuna fetch failed: {type(exc).__name__}",
            )

        try:
            payload = response.json()
        except ValueError:
            return AdapterFetchResult(fetch_url=url, error="invalid Adzuna JSON payload")

        items = payload.get("results")
        if not isinstance(items, list):
            return AdapterFetchResult(
                fetch_url=url,
                error="Adzuna payload did not contain a results list",
            )

        jobs = []
        for item in items:
            if not isinstance(item, dict):
                continue
            job = self._normalize_item(source, item)
            if job is not None:
                jobs.append(job)
        return AdapterFetchResult(
            fetch_url=url,
            jobs=jobs,
            raw_payload={
                "count": payload.get("count"),
                "total": payload.get("total"),
            },
        )

    def _normalize_item(self, source: JobSource, item: dict[str, Any]) -> NormalizedJob | None:
        item_url = (item.get("redirect_url") or "").strip()
        if not item_url:
            return None
        company = item.get("company")
        company_name: str | None = None
        company_url: str | None = None
        if isinstance(company, dict):
            company_name = _as_text(company.get("display_name")) or None
            company_url = _as_text(company.get("url")) or None
        location = item.get("location")
        location_name: str | None = None
        if isinstance(location, dict):
            location_name = _as_text(location.get("display_name")) or None
        return self.normalizer.as_normalized_job(
            title=_as_text(item.get("title")),
            url=item_url,
            base_url=source.base_url,
            external_id=_as_text(item.get("id")) or None,
            location=location_name,
            description=_as_text(item.get("description")) or None,
            company_name=company_name,
            company_domain=domain_of(company_url) if company_url else None,
            posted_at=parse_utc(item.get("created")),
        )
