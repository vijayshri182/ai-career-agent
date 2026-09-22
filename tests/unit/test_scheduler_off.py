"""Tests for the scheduler being OFF by default and explicit-start-only.

The product must never crawl or trigger discovery on its own: the default
configuration disables scheduled discovery, the in-process scheduler only acts
after an explicit ``start()``, and the application lifespan starts nothing when
``DISCOVERY_ENABLED`` is false.
"""

from types import SimpleNamespace
from uuid import uuid4

from backend.app.main import app, lifespan
from backend.core.config import Settings
from backend.services.scheduler import AgentScheduler


def _candidate() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), user_id=uuid4())


def test_discovery_disabled_by_default() -> None:
    settings = Settings(_env_file=None)
    assert settings.discovery_enabled is False


async def test_scheduler_is_inert_until_started() -> None:
    calls: list[tuple[uuid4, uuid4]] = []

    async def run_fn(candidate_id, user_id):
        calls.append((candidate_id, user_id))

    async def get_candidates():
        return [_candidate()]

    async def get_sources(candidate_id):
        return [object()]

    scheduler = AgentScheduler(
        interval_seconds=60,
        run_fn=run_fn,
        get_candidates=get_candidates,
        get_sources=get_sources,
    )

    assert not scheduler.running
    assert calls == []

    await scheduler.trigger_now()
    assert len(calls) == 1

    scheduler.start()
    assert scheduler.running
    scheduler.stop()
    assert not scheduler.running
    assert len(calls) == 1


async def test_scheduler_skips_candidates_without_sources() -> None:
    calls: list[tuple[uuid4, uuid4]] = []

    async def run_fn(candidate_id, user_id):
        calls.append((candidate_id, user_id))

    async def get_candidates():
        return [_candidate()]

    async def get_sources(candidate_id):
        return []

    scheduler = AgentScheduler(
        interval_seconds=60,
        run_fn=run_fn,
        get_candidates=get_candidates,
        get_sources=get_sources,
    )
    await scheduler.trigger_now()
    assert calls == []


async def test_lifespan_starts_no_scheduler_when_disabled() -> None:
    async with lifespan(app):
        assert getattr(app.state, "scheduler", None) is None
