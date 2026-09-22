"""Lightweight in-process job-discovery scheduler.

When ``DISCOVERY_ENABLED=True`` the scheduler periodically scans for active
candidates that have enabled job sources and triggers a discovery run per
candidate. The scheduler does nothing by default; it must be explicitly started
via ``AgentScheduler.start()`` (typically in the FastAPI lifespan).

Runs are serialized so at most one discovery per candidate runs concurrently.
Crawl rate-limits and robots.txt are enforced per source inside the discovery
service, not here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)


class AgentScheduler:
    """Async task scheduler driving periodic job-discovery runs."""

    def __init__(
        self,
        *,
        interval_seconds: int,
        run_fn: Callable[[UUID, UUID], Awaitable[object]],
        get_candidates: Callable[[], Awaitable[list[Any]]],
        get_sources: Callable[[UUID], Awaitable[list[Any]]],
    ) -> None:
        self._interval = interval_seconds
        self._run_fn = run_fn
        self._get_candidates = get_candidates
        self._get_sources = get_sources
        self._task: asyncio.Task[object] | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self.running:
            return
        self._task = asyncio.create_task(self._loop(), name="agent-scheduler")
        logger.info("agent.scheduler_started", interval_seconds=self._interval)

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
            logger.info("agent.scheduler_stopped")

    async def trigger_now(self) -> None:
        await self._tick()

    async def _loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._interval)
                await self._tick()
        except asyncio.CancelledError:
            pass

    async def _tick(self) -> None:
        try:
            candidates = await self._get_candidates()
        except Exception:  # noqa: BLE001
            logger.exception("agent.scheduler_load_failed")
            return
        for candidate in candidates:
            try:
                sources = await self._get_sources(candidate.id)
                if not sources:
                    continue
                await self._run_fn(candidate.id, candidate.user_id)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "agent.discovery_run_failed", candidate_id=str(candidate.id)
                )
