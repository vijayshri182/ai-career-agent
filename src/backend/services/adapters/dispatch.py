"""Route a job source to the adapter that understands its ``mode``.

Discovery receives one adapter (built by an adapter factory) and calls its
``fetch`` with a job source. This dispatcher lets distinct sources use
dedicated adapters (for example the Adzuna API) while everything else falls
back to the generic HTTP/JSON adapter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.services.adapters.base import AdapterFetchResult, JobSourceAdapter

if TYPE_CHECKING:
    from backend.models.job_source import JobSource


class RoutingAdapter:
    """Delegates ``fetch`` by ``source.crawl_config["mode"]``."""

    def __init__(
        self,
        default: JobSourceAdapter,
        specialized: dict[str, JobSourceAdapter],
    ) -> None:
        self.default = default
        self.specialized = specialized

    async def fetch(self, source: JobSource) -> AdapterFetchResult:
        mode = (source.crawl_config or {}).get("mode")
        key = mode if isinstance(mode, str) else ""
        adapter = self.specialized.get(key, self.default)
        return await adapter.fetch(source)
