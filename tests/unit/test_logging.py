"""Tests for structured (JSON) logging configuration."""

import io
import json
from uuid import uuid4

import structlog

from backend.core.logging_utils import configure_logging


def test_configure_logging_emits_json() -> None:
    stream = io.StringIO()
    configure_logging(log_level="DEBUG", file=stream, force=True)
    structlog.get_logger(f"backend.test.{uuid4().hex}").info(
        "test.event", detail={"tube": 7}, code="abc"
    )
    line = stream.getvalue().strip().splitlines()[0]
    event = json.loads(line)
    assert event["event"] == "test.event"
    assert event["level"] == "info"
    assert event["detail"] == {"tube": 7}
    assert event["code"] == "abc"
    assert "timestamp" in event


def test_configure_logging_respects_level() -> None:
    stream = io.StringIO()
    configure_logging(log_level="ERROR", file=stream, force=True)
    structlog.get_logger(f"backend.test.{uuid4().hex}").info("skipped.event")
    assert stream.getvalue() == ""
