"""Integration tests for the recruiter contact discovery API."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Depends
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_recruiter_discovery_service, get_session
from backend.app.main import app
from backend.repositories.audit import AuditRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.company import CompanyRepository
from backend.repositories.job import JobRepository
from backend.repositories.job_source import JobSourceRepository
from backend.repositories.recruiter_contact import (
    ContactSourceRepository,
    RecruiterContactRepository,
)
from backend.services.recruiter_directory import DirectoryPerson, RecruiterDirectoryFetcher
from backend.services.recruiter_discovery import RecruiterDiscoveryService


class _FakeFetcher(RecruiterDirectoryFetcher):
    def __init__(self, people: list[DirectoryPerson]) -> None:
        self._people = people

    async def fetch(self, company, job) -> list[DirectoryPerson]:
        return self._people


def _build_override(candidate, user, people: list[DirectoryPerson]):
    fetcher = _FakeFetcher(people)

    def _get_service(session: AsyncSession = Depends(get_session)) -> RecruiterDiscoveryService:
        return RecruiterDiscoveryService(
            candidate_repo=CandidateRepository(session),
            job_repo=JobRepository(session),
            company_repo=CompanyRepository(session),
            contact_repo=RecruiterContactRepository(session),
            source_repo=ContactSourceRepository(session),
            audit_repo=AuditRepository(session),
            actor_id=user.id,
            candidate_id=candidate.id,
            directory_fetcher=fetcher,
        )

    return _get_service


def _verified_person(handle: str, *, email_publicly_listed: bool = False) -> DirectoryPerson:
    return DirectoryPerson(
        full_name="Alex Rivera",
        role_title="Talent Acquisition Recruiter",
        profile_url=f"https://careers.test/profile/{handle}",
        company_domain="acme.test",
        email_publicly_listed=email_publicly_listed,
        email="alex@acme.test" if email_publicly_listed else None,
    )


def _guessed_person(handle: str) -> DirectoryPerson:
    return DirectoryPerson(
        full_name="Casey Kim",
        role_title="Recruiter",
        profile_url=f"https://unknown.test/profile/{handle}",
        company_domain="unrelated.test",
    )


async def _seed_job(session: AsyncSession, candidate_id, cid: str) -> str:
    company = await CompanyRepository(session).get_or_create_by_domain(
        name="Acme Networks", domain="acme.test"
    )
    source_repo = JobSourceRepository(session)
    sources = await source_repo.list_for_candidate(candidate_id)
    source = next((s for s in sources if s.name == "Careers API"), None)
    if source is None:
        source = await source_repo.create(
            candidate_id=candidate_id,
            name="Careers API",
            source_type="api",
            base_url="https://careers.test",
            terms_allow_automation=True,
            is_enabled=True,
        )
    now = datetime.now(UTC)
    job = await JobRepository(session).create(
        candidate_id=candidate_id,
        company_id=company.id,
        source_id=source.id,
        url=f"https://careers.test/jobs/{cid}",
        title="Senior Software Engineer",
        location="Bangalore, India",
        description="Qualifications:\n- 5+ years of software engineering\n",
        content_hash=f"hash-{cid}",
        first_seen_at=now,
        last_seen_at=now,
    )
    return str(job.id)


async def test_discover_surfaces_only_verified_contacts(
    client: AsyncClient, candidate, test_user, auth_headers, session: AsyncSession
):
    app.dependency_overrides[get_recruiter_discovery_service] = _build_override(
        candidate, test_user, [_verified_person("api-v1"), _guessed_person("api-g1")]
    )
    job_id = await _seed_job(session, candidate.id, "rc1")
    cid = str(candidate.id)

    resp = await client.post(
        f"/api/v1/candidates/{cid}/jobs/{job_id}/discover-contacts", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["found"] == 2
    assert body["created"] == 1
    assert body["hidden"] == 1

    listed = await client.get(
        f"/api/v1/candidates/{cid}/recruiter-contacts", headers=auth_headers
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["full_name"] == "Alex Rivera"
    assert listed.json()["items"][0]["contact_type"] == "verified"
    assert listed.json()["items"][0]["confidence_score"] == 95
    assert listed.json()["items"][0]["source_id"] is not None
    app.dependency_overrides.pop(get_recruiter_discovery_service, None)


async def test_guessed_email_never_returned(
    client: AsyncClient, candidate, test_user, auth_headers, session: AsyncSession
):
    app.dependency_overrides[get_recruiter_discovery_service] = _build_override(
        candidate,
        test_user,
        [
            _verified_person("rc-noemail", email_publicly_listed=False),
            _guessed_person("rc-g2"),
        ],
    )
    job_id = await _seed_job(session, candidate.id, "rc2")
    cid = str(candidate.id)
    resp = await client.post(
        f"/api/v1/candidates/{cid}/jobs/{job_id}/discover-contacts", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    listed = await client.get(
        f"/api/v1/candidates/{cid}/recruiter-contacts", headers=auth_headers
    )
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["email"] is None
    assert items[0]["public_profile_url"].endswith("rc-noemail")
    app.dependency_overrides.pop(get_recruiter_discovery_service, None)


async def test_discovery_and_listing_are_candidate_scoped(
    client: AsyncClient, candidate, test_user, auth_headers, session: AsyncSession
):
    app.dependency_overrides[get_recruiter_discovery_service] = _build_override(
        candidate, test_user, [_verified_person("rc-scope")]
    )
    job_id = await _seed_job(session, candidate.id, "rc3")
    cid = str(candidate.id)
    resp = await client.post(
        f"/api/v1/candidates/{cid}/jobs/{job_id}/discover-contacts", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text

    # Unknown candidate id -> 404 from the ownership gate, never data.
    other = str(uuid4())
    resp = await client.get(
        f"/api/v1/candidates/{other}/recruiter-contacts", headers=auth_headers
    )
    assert resp.status_code == 404
    resp = await client.post(
        f"/api/v1/candidates/{other}/jobs/{job_id}/discover-contacts", headers=auth_headers
    )
    assert resp.status_code == 404
    app.dependency_overrides.pop(get_recruiter_discovery_service, None)


async def test_unknown_job_discovery_is_404(
    client: AsyncClient, candidate, test_user, auth_headers
):
    app.dependency_overrides[get_recruiter_discovery_service] = _build_override(
        candidate, test_user, []
    )
    cid = str(candidate.id)
    resp = await client.post(
        f"/api/v1/candidates/{cid}/jobs/{uuid4()}/discover-contacts", headers=auth_headers
    )
    assert resp.status_code == 404
    app.dependency_overrides.pop(get_recruiter_discovery_service, None)
