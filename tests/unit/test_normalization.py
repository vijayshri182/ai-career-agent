"""Unit tests for job content normalization and hashing."""

from backend.services.normalization import JobNormalizer, domain_of, parse_utc


def _norm() -> JobNormalizer:
    return JobNormalizer()


class TestNormalizeText:
    def test_collapse_whitespace(self) -> None:
        assert _norm().normalize_text("  hello   world\n") == "hello world"

    def test_html_entities(self) -> None:
        assert _norm().normalize_text("big &amp; bold") == "big & bold"

    def test_nbsp_replaced(self) -> None:
        assert _norm().normalize_text("a\u00a0b") == "a b"

    def test_none_returns_empty(self) -> None:
        assert _norm().normalize_text(None) == ""


class TestCleanOptional:
    def test_falsey_strings_to_none(self) -> None:
        for val in ("", "n/a", "N/A", "none", "unknown", "-", "null", "NA"):
            assert _norm().clean_optional(val) is None

    def test_valid_text_kept(self) -> None:
        assert _norm().clean_optional("San Francisco") == "San Francisco"


class TestContentHash:
    def test_same_inputs_same_hash(self) -> None:
        h = _norm().content_hash("Senior Engineer", "NYC", "Great role")
        assert _norm().content_hash("Senior Engineer", "NYC", "Great role") == h

    def test_different_inputs_different_hash(self) -> None:
        h1 = _norm().content_hash("A", None, None)
        h2 = _norm().content_hash("B", None, None)
        assert h1 != h2


class TestResolveUrl:
    def test_absolute_passthrough(self) -> None:
        assert _norm().resolve_url("https://x.com/j", "https://base.com") == "https://x.com/j"

    def test_relative_joined(self) -> None:
        assert _norm().resolve_url("/jobs", "https://base.com/feed") == "https://base.com/jobs"

    def test_javascript_returns_empty(self) -> None:
        assert _norm().resolve_url("javascript:void(0)", "https://x.com") == ""

    def test_anchor_stripped(self) -> None:
        assert _norm().resolve_url("/j#section", "https://x.com") == "https://x.com/j"


class TestAsNormalizedJob:
    def test_returns_none_if_empty_title(self) -> None:
        assert _norm().as_normalized_job(title="", url="/j", base_url="https://x.com") is None

    def test_returns_none_if_empty_url(self) -> None:
        assert _norm().as_normalized_job(title="Eng", url="javascript:void(0)", base_url="https://x.com") is None

    def test_happy_path(self) -> None:
        job = _norm().as_normalized_job(
            title="Engineer",
            url="/jobs/123",
            base_url="https://careers.example.com",
            company_name="Acme Corp",
            location="NYC",
        )
        assert job is not None
        assert job.title == "Engineer"
        assert job.company_name == "Acme Corp"
        assert len(job.content_hash) == 64


class TestParseUtc:
    def test_none(self) -> None:
        assert parse_utc(None) is None

    def test_unix_epoch(self) -> None:
        from datetime import UTC, datetime

        dt = parse_utc(0)
        assert dt == datetime(1970, 1, 1, tzinfo=UTC)

    def test_iso8601_z(self) -> None:

        dt = parse_utc("2024-01-01T00:00:00Z")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_malformed_returns_none(self) -> None:
        assert parse_utc("not-a-date") is None


class TestDomainOf:
    def test_strips_www(self) -> None:
        assert domain_of("https://www.example.com/jobs") == "example.com"

    def test_returns_none_for_no_host(self) -> None:
        assert domain_of("") is None
