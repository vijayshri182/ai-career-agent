"""Source URL validation (allow-list style) for job discovery.

Guards against malformed and dangerous targets without resolving DNS: the
scheme must be http(s), URLs must not embed credentials, and literal IP
addresses in loopback/private/link-local/reserved ranges are rejected. Hostname
resolution is intentionally not performed here (that would hand an attacker
the backend's DNS); production deployments should additionally egress through a
restricted proxy.
"""

import ipaddress
from urllib.parse import urlsplit

from backend.core.exceptions import ValidationError

_ALLOWED_SCHEMES = {"http", "https"}


def validate_source_url(url: str) -> str:
    """Validate a job source URL, raising ``ValidationError`` when unsafe."""
    try:
        parts = urlsplit(url.strip())
    except ValueError as exc:
        raise ValidationError("Invalid URL") from exc

    if parts.scheme not in _ALLOWED_SCHEMES:
        raise ValidationError("Source URL must use http or https")
    if not parts.hostname:
        raise ValidationError("Source URL must include a hostname")
    if parts.username or parts.password:
        raise ValidationError("Source URL must not embed credentials")

    host = parts.hostname.lower().rstrip(".")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # Not a literal IP; leave hostname (DNS) validation to deployment egress rules.
        return url.strip()

    _reject_private(address)
    return url.strip()


def _reject_private(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    if (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    ):
        raise ValidationError("Source URL must not point to a private network address")
