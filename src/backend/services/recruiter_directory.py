"""Recruiter directory fetch abstraction.

Keeps the discovery service network-free by default: the production harness
plugs a real public-directory fetcher behind :class:`RecruiterDirectoryFetcher`,
which MUST only query public career/team pages and public directories. The
default fetcher returns nothing, so a discovery run is a no-op until such an
adapter is provided — matching the "foundation first, adapters later" pattern
used by job discovery.
"""

from dataclasses import dataclass
from typing import Protocol

from backend.models.company import Company
from backend.models.job import Job


@dataclass
class DirectoryPerson:
    """One public directory entry. ``email_publicly_listed`` may only be True
    when the public source explicitly exposed the address."""

    full_name: str
    role_title: str
    profile_url: str
    company_domain: str | None = None
    email_publicly_listed: bool = False
    email: str | None = None


class RecruiterDirectoryFetcher(Protocol):
    async def fetch(self, company: Company, job: Job) -> list[DirectoryPerson]: ...


class EmptyDirectoryFetcher:
    """Default: no public directory is queried; a discovery run finds nothing."""

    async def fetch(self, company: Company, job: Job) -> list[DirectoryPerson]:
        return []


def make_directory_fetcher() -> RecruiterDirectoryFetcher:
    return EmptyDirectoryFetcher()
