"""Structured (JSON) logging configuration.

App-level loggers emit one JSON object per line with a timestamp and level.
Stdlib loggers (for example uvicorn) keep their own handlers; this is additive
configuration applied once at bootstrap so it never mutates third-party output.
"""

from __future__ import annotations

import logging
import sys
from typing import TextIO

import structlog

_configured = False


def configure_logging(
    *, log_level: str = "INFO", file: TextIO = sys.stderr, force: bool = False
) -> None:
    """Apply structured logging (idempotent; ``force`` reconfigures for tests)."""
    global _configured
    if _configured and not force:
        return
    _configured = True

    level = getattr(logging, log_level.upper(), logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=file),
        cache_logger_on_first_use=True,
    )
