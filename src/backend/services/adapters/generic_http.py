"""Generic HTTP/JSON job-feed adapter.

Reads a `JobSource.crawl_config` with the following shape:

```json
{
  "mode": "json",
  "feed_url": "https://jobs.example.com/feed",
  "list_path": "jobs",
  "selectors": {
    "title": "title",
    "url": "absolute_url",
    "external_id": "id",
    "location": "location.name",
    "description": "description_plain",
    "company_name": "company.name"
  }
}
```

HTML mode (`"mode": "html"`) best-effort extracts same-origin anchors whose
href or text look like job postings. External content is always treated as
untrusted data: extraction failures degrade to a `None`/zero-job result and are
recorded, never raised.
"""

import json
from typing import Any

import httpx

from backend.models.job_source import JobSource
from backend.services.adapters.base import AdapterFetchResult
from backend.services.normalization import JobNormalizer, NormalizedJob, domain_of, parse_utc

_JOB_HINT = ("job", "careers", "positions", "openings", "vacanc", "requisition", "opportunit")


class GenericHttpAdapter:
    """Dependency-light adapter supporting JSON feeds and HTML anchor pages."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        normalizer: JobNormalizer,
        *,
        user_agent: str,
        timeout: float,
    ) -> None:
        self.client = client
        self.normalizer = normalizer
        self.user_agent = user_agent
        self.timeout = timeout

    async def fetch(self, source: JobSource) -> AdapterFetchResult:
        config = source.crawl_config or {}
        mode = config.get("mode", "json")
        feed_url = str(config.get("feed_url") or source.base_url)
        headers = {"User-Agent": self.user_agent}
        configured_headers = config.get("headers")
        if isinstance(configured_headers, dict):
            for key, value in configured_headers.items():
                if isinstance(value, str):
                    headers[key] = value

        try:
            response = await self.client.get(feed_url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            return AdapterFetchResult(
                fetch_url=feed_url, error=f"fetch failed: {type(exc).__name__}"
            )

        if mode == "json":
            return self._extract_json(source, feed_url, response)
        return self._extract_html(source, feed_url, response)

    def _extract_json(
        self, source: JobSource, feed_url: str, response: httpx.Response
    ) -> AdapterFetchResult:
        config = source.crawl_config or {}
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError):
            return AdapterFetchResult(fetch_url=feed_url, error="invalid JSON payload")

        items = _get_path(payload, config.get("list_path", "jobs"))
        if not isinstance(items, list):
            return AdapterFetchResult(fetch_url=feed_url, error="list_path did not resolve to a list")

        selectors = config.get("selectors")
        if not isinstance(selectors, dict):
            selectors = {}
        jobs: list[NormalizedJob] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            job = self.normalizer.as_normalized_job(
                title=_str_field(item, selectors, "title"),
                url=_str_field(item, selectors, "url") or _str_field(item, selectors, "link"),
                base_url=source.base_url,
                external_id=_str_field(item, selectors, "external_id"),
                location=_str_field(item, selectors, "location"),
                description=_str_field(item, selectors, "description"),
                company_name=_str_field(item, selectors, "company_name"),
                company_domain=_str_field(item, selectors, "company_domain"),
                posted_at=parse_utc(_get_path(item, selectors.get("posted_at"))),
                closing_at=parse_utc(_get_path(item, selectors.get("closing_at"))),
            )
            if job is not None:
                jobs.append(job)
        return AdapterFetchResult(fetch_url=feed_url, jobs=jobs, raw_payload=payload)

    def _extract_html(
        self, source: JobSource, feed_url: str, response: httpx.Response
    ) -> AdapterFetchResult:
        text = response.text or ""
        links = _anchors(text)
        origin = _origin_of(source.base_url)
        company_domain = domain_of(source.base_url)
        jobs: list[NormalizedJob] = []
        seen: set[str] = set()
        for href, anchor_text in links:
            target = self.normalizer.resolve_url(href, source.base_url)
            if not target or target in seen or (origin and not target.startswith(origin)):
                continue
            hint = f"{anchor_text} {target}".lower()
            if not any(word in hint for word in _JOB_HINT):
                continue
            seen.add(target)
            job = self.normalizer.as_normalized_job(
                title=anchor_text or target,
                url=target,
                base_url=source.base_url,
                company_domain=company_domain,
                external_id=target.rsplit("/", 1)[-1],
            )
            if job is not None:
                jobs.append(job)
        return AdapterFetchResult(
            fetch_url=feed_url,
            jobs=jobs,
            raw_payload={"sample": self.normalizer.normalize_text(text)[:2000]},
        )


def _get_path(obj: Any, path: object) -> Any:
    if not isinstance(path, str) or not path:
        return None
    current = obj
    for segment in path.split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        else:
            return None
    return current


def _str_field(item: dict[str, Any], selectors: dict[Any, Any], field: str) -> str:
    value = _get_path(item, selectors.get(field))
    if isinstance(value, str):
        return value
    if isinstance(value, int | float):
        return str(value)
    return ""


def _origin_of(url: str) -> str | None:
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def _anchors(html: str) -> list[tuple[str, str]]:
    from html.parser import HTMLParser

    class _AnchorParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.links: list[tuple[str, str]] = []
            self._href: str | None = None
            self._depth = 0

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag == "a":
                self._depth += 1
                for key, value in attrs:
                    if key == "href":
                        self._href = value or ""

        def handle_endtag(self, tag: str) -> None:
            if tag == "a" and self._depth > 0:
                self._depth -= 1

        def handle_data(self, data: str) -> None:
            if self._href is not None and self._depth > 0:
                self.links.append((self._href, data.strip()))
                self._href = None

    parser = _AnchorParser()
    try:
        parser.feed(html)
    except Exception:
        return []
    return parser.links
