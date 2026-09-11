"""Unit tests for job source URL validation."""

import pytest

from backend.core.exceptions import ValidationError
from backend.services.url_validation import validate_source_url


@pytest.mark.parametrize(
    "url",
    [
        "https://careers.example.com/jobs",
        "http://example.com",
        "  https://jobs.example.org/positions?q=eng  ",
    ],
)
def test_accepts_public_http_urls(url: str) -> None:
    assert validate_source_url(url) == url.strip()


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "",
        "not-a-url",
    ],
)
def test_rejects_bad_scheme(url: str) -> None:
    with pytest.raises(ValidationError):
        validate_source_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://user:pass@example.com/jobs",
        "https://user@example.com",
    ],
)
def test_rejects_embedded_credentials(url: str) -> None:
    with pytest.raises(ValidationError):
        validate_source_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/jobs",
        "https://10.0.0.5",
        "https://192.168.1.1/jobs",
        "https://169.254.169.254/latest/meta-data",
        "http://[::1]/jobs",
    ],
)
def test_rejects_private_ip_targets(url: str) -> None:
    with pytest.raises(ValidationError):
        validate_source_url(url)
