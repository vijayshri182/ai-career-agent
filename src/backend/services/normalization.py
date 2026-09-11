"""Job content normalization and fingerprinting."""

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

_FALSEY_TEXT = {"", "unknown", "n/a", "na", "null", "none", "-"}


@dataclass
class NormalizedJob:
    """Structured, normalized representation of one discovered posting."""

    title: str
    url: str
    external_id: str | None = None
    location: str | None = None
    description: str | None = None
    company_name: str | None = None
    company_domain: str | None = None
    posted_at: datetime | None = None
    closing_at: datetime | None = None
    content_hash: str = ""


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "template"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "template"} and self._skip > 0:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip == 0:
            self.parts.append(data)


class JobNormalizer:
    """Pure functions turning untrusted feed content into clean text/hashes."""

    def extract_html_text(self, html: str) -> str:
        parser = _TextExtractor()
        try:
            parser.feed(html)
        except Exception:  # malformed HTML must never break discovery
            return ""
        return self.normalize_text(" ".join(parser.parts))

    def normalize_text(self, value: str | None) -> str:
        if not value:
            return ""
        text = unescape(value).replace("\u00a0", " ")
        return " ".join(text.split())

    def clean_optional(self, value: str | None) -> str | None:
        normalized = self.normalize_text(value)
        if normalized.lower() in _FALSEY_TEXT:
            return None
        return normalized or None

    def content_hash(self, title: str, location: str | None, description: str | None) -> str:
        fingerprint = "|".join(
            [
                self.normalize_text(title).lower(),
                self.normalize_text(location).lower(),
                self.normalize_text(description).lower(),
            ]
        )
        return sha256(fingerprint.encode("utf-8")).hexdigest()

    def resolve_url(self, link: str, base_url: str) -> str:
        if link.startswith("javascript:") or link.startswith("#"):
            return ""
        return urljoin(base_url, link).split("#", 1)[0]

    def as_normalized_job(
        self,
        *,
        title: str,
        url: str,
        base_url: str,
        external_id: str | None = None,
        location: str | None = None,
        description: str | None = None,
        company_name: str | None = None,
        company_domain: str | None = None,
        posted_at: datetime | None = None,
        closing_at: datetime | None = None,
    ) -> NormalizedJob | None:
        clean_title = self.normalize_text(title)
        resolved = self.resolve_url(url, base_url)
        if not clean_title or not resolved:
            return None
        clean_location = self.clean_optional(location)
        clean_description = self.clean_optional(description)
        return NormalizedJob(
            title=clean_title,
            url=resolved,
            external_id=self.clean_optional(external_id),
            location=clean_location,
            description=clean_description,
            company_name=self.clean_optional(company_name),
            company_domain=self.clean_optional(company_domain),
            posted_at=posted_at,
            closing_at=closing_at,
            content_hash=self.content_hash(clean_title, clean_location, clean_description),
        )


def parse_utc(value: Any) -> datetime | None:
    """Best-effort parse of a feed timestamp to an aware UTC datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, tz=UTC)
    text = str(value).strip()
    if not text:
        return None
    # ISO 8601 with optional fractional seconds / Z suffix.
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def domain_of(url: str) -> str | None:
    from urllib.parse import urlsplit

    host = urlsplit(url).hostname
    if not host:
        return None
    host = host.lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host or None
