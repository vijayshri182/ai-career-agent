"""Job source adapters package."""

from backend.services.adapters.adzuna import AdzunaAdapter
from backend.services.adapters.base import AdapterFetchResult, JobSourceAdapter
from backend.services.adapters.dispatch import RoutingAdapter
from backend.services.adapters.generic_http import GenericHttpAdapter

__all__ = [
    "AdapterFetchResult",
    "AdzunaAdapter",
    "GenericHttpAdapter",
    "JobSourceAdapter",
    "RoutingAdapter",
]
