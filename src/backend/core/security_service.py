"""Lazy singleton for SecurityService."""

from backend.core.config import Settings, get_settings
from backend.core.security import SecurityService

_security_service: SecurityService | None = None


def get_security_service(settings: Settings | None = None) -> SecurityService:
    """Return the configured SecurityService, creating it if necessary."""
    global _security_service
    if _security_service is None:
        _security_service = SecurityService(settings or get_settings())
    return _security_service
