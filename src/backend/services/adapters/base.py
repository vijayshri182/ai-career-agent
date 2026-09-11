"""Job source adapter protocol and shared result type."""

from dataclasses import dataclass, field
from typing import Protocol

from backend.models.job_source import JobSource
from backend.services.normalization import NormalizedJob


@dataclass
class AdapterFetchResult:
    """Outcome of one source fetch + extraction pass."""

    fetch_url: str
    jobs: list[NormalizedJob] = field(default_factory=list)
    raw_payload: dict[str, object] = field(default_factory=dict)
    error: str | None = None


class JobSourceAdapter(Protocol):
    """Contract implemented by feed-format adapters."""

    async def fetch(self, source: JobSource) -> AdapterFetchResult:
        """Fetch the source and normalize its payload into ``NormalizedJob``s."""
