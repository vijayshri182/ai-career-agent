"""Unit tests for the recruiter discovery service."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import NotFoundError
from backend.models.recruiter_contact import RecruiterContact
from backend.services.recruiter_directory import DirectoryPerson, RecruiterDirectoryFetcher
from backend.services.recruiter_discovery import RecruiterDiscoveryService


class _StubFetcher(RecruiterDirectoryFetcher):
    def __init__(self, people: list[DirectoryPerson]) -> None:
        self._people = people

    async def fetch(self, company, job) -> list[DirectoryPerson]:
        return self._people


class _EmptyFetcher(RecruiterDirectoryFetcher):
    async def fetch(self, company, job) -> list[DirectoryPerson]:
        return []


def _service(
    session: AsyncSession,
    candidate,
    user,
    *,
    fetcher: RecruiterDirectoryFetcher,
    candidate_id=None,
) -> RecruiterDiscoveryService:
    from backend.repositories.audit import AuditRepository
    from backend.repositories.candidate import CandidateRepository
    from backend.repositories.company import CompanyRepository
    from backend.repositories.job import JobRepository
    from backend.repositories.recruiter_contact import (
        ContactSourceRepository,
        RecruiterContactRepository,
    )

    return RecruiterDiscoveryService(
        candidate_repo=CandidateRepository(session),
        job_repo=JobRepository(session),
        company_repo=CompanyRepository(session),
        contact_repo=RecruiterContactRepository(session),
        source_repo=ContactSourceRepository(session),
        audit_repo=AuditRepository(session),
        actor_id=user.id,
        candidate_id=candidate_id or candidate.id,
        directory_fetcher=fetcher,
    )


async def _seed_job(session: AsyncSession, candidate_id, cid: str):
    from backend.repositories.company import CompanyRepository
    from backend.repositories.job import JobRepository
    from backend.repositories.job_source import JobSourceRepository

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
    return await JobRepository(session).create(
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


async def test_empty_discovery_run_finds_nothing(session, candidate, test_user):
    job = await _seed_job(session, candidate.id, "wd1")
    service = _service(session, candidate, test_user, fetcher=_EmptyFetcher())
    summary = await service.discover_for_job(job.id)
    await session.commit()
    assert summary.found == 0
    assert summary.created == 0
    items, total = await service.list_contacts()
    assert total == 0 and items == []


async def test_verified_contacts_surfaced_guesses_hidden(session, candidate, test_user):
    job = await _seed_job(session, candidate.id, "wd2")
    service = _service(
        session,
        candidate,
        test_user,
        fetcher=_StubFetcher([_verified_person("v1"), _guessed_person("g1")]),
    )
    summary = await service.discover_for_job(job.id)
    await session.commit()
    assert summary.found == 2
    assert summary.created == 1
    assert summary.hidden == 1

    items, total = await service.list_contacts()
    assert total == 1
    assert items[0].full_name == "Alex Rivera"
    assert items[0].contact_type == "verified"
    assert items[0].confidence_score == 95
    assert items[0].is_suppressed is False
    assert items[0].source_id is not None


async def test_guessed_email_is_never_stored(session, candidate, test_user):
    job = await _seed_job(session, candidate.id, "wd3")
    service = _service(
        session,
        candidate,
        test_user,
        fetcher=_StubFetcher(
            [
                # This person's email was NOT publicly listed -> must not be stored.
                _verified_person("no-email", email_publicly_listed=False),
                # This person's email WAS publicly listed -> may be stored.
                _verified_person("listed", email_publicly_listed=True),
            ]
        ),
    )
    summary = await service.discover_for_job(job.id)
    await session.commit()
    assert summary.created == 2
    stored: list[RecruiterContact] = (await service.list_contacts())[0]
    by_url = {c.public_profile_url.split("/")[-1]: c for c in stored}
    assert by_url["no-email"].email is None
    assert by_url["listed"].email == "alex@acme.test"


async def test_second_discovery_run_dedupes(session, candidate, test_user):
    job = await _seed_job(session, candidate.id, "wd4")
    fetcher = _StubFetcher([_verified_person("v4")])
    service = _service(session, candidate, test_user, fetcher=fetcher)
    first = await service.discover_for_job(job.id)
    await session.commit()
    second = await service.discover_for_job(job.id)
    await session.commit()
    assert first.created == 1
    assert second.created == 0
    assert second.existing_skipped == 1
    items, total = await service.list_contacts()
    assert total == 1


async def test_other_candidate_cannot_read_contacts(session, candidate, test_user):
    job = await _seed_job(session, candidate.id, "wd5")
    service = _service(
        session, candidate, test_user, fetcher=_StubFetcher([_verified_person("v5")])
    )
    await service.discover_for_job(job.id)
    await session.commit()
    items, _ = await service.list_contacts()
    contact_id = items[0].id if items else uuid4()

    stranger = _service(
        session,
        candidate,
        test_user,
        fetcher=_EmptyFetcher(),
        candidate_id=uuid4(),
    )
    with pytest.raises(NotFoundError):
        await stranger.discover_for_job(job.id)
    with pytest.raises(NotFoundError):
        await stranger.get_contact(contact_id)
    with pytest.raises(NotFoundError):
        await stranger.list_contacts()


async def test_unknown_job_is_404(session, candidate, test_user):
    service = _service(session, candidate, test_user, fetcher=_EmptyFetcher())
    with pytest.raises(NotFoundError):
        await service.discover_for_job(uuid4())
    await session.commit()
