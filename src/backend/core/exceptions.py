"""Domain and HTTP exceptions."""


class NotFoundError(Exception):
    """Resource not found."""


class ForbiddenError(Exception):
    """Action not permitted for current actor."""


class ValidationError(Exception):
    """Domain validation error."""


def http_status_for(exc: Exception) -> int:
    if isinstance(exc, NotFoundError):
        return 404
    if isinstance(exc, ForbiddenError):
        return 403
    if isinstance(exc, ValidationError):
        return 400
    return 500
