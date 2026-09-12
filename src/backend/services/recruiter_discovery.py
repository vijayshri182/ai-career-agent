"""Recruiter contact discovery service.

Discovers legitimate, publicly available recruiting contacts for a target job's
company, scores their affiliation, and persists only contacts that clear the
privacy/safety boundaries:

* Only VERIFIED affiliations scoring >= 70 are surfaced (guessed/low-confidence
  contacts are stored but suppressed and never listed).
* Guessed email addresses are never stored: ``email`` is only persisted when a
  public source explicitly listed it (``DirectoryPerson.email_publicly_listed``).
* Each surfaced contact carries its public evidence URL and a ``ContactSource``
  row describing the source page.

Discovery uses an injectable ``RecruiterDirectoryFetcher`` (default: nothing), so
a run is a network-free no-op until a real public-directory adapter is provided.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from backend.core.exceptions import NotFoundError
from backend.models.company import Company
from backend.models.job import Job
from backend.models.recruiter_contact import (
    ContactSourceType,
    ContactType,
    RecruiterContact,
)
from backend.repositories.audit import AuditRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.company import CompanyRepository
from backend.repositories.job import JobRepository
from backend.repositories.recruiter_contact import (
    ContactSourceRepository,
    RecruiterContactRepository,
)
from backend.services.recruiter_confidence import AffiliationConfidenceScorer
from backend.services.recruiter_directory import (
    DirectoryPerson,
    RecruiterDirectoryFetcher,
    make_directory_fetcher,
)


@dataclass
class DiscoverySummary:
    """Result of one discovery run."""

    found: int = 0
    created: int = 0
    existing_skipped: int = 0
    hidden: int = 0
    contacts: list[RecruiterContact] = field(default_factory=list)


def _on_company_domain(website_domain: str | None, person_domain: str | None) -> bool:
    """A directory entry only counts as company-owned evidence when its stated
    domain matches the company's verified domain. Missing or unrelated domains
    never earn verified credit (privacy-first affiliation check)."""
    if not website_domain or not person_domain:
        return False
    base = website_domain.lower().strip().rstrip("/")
    claimed = person_domain.lower().strip().rstrip("/")
    return claimed == base or claimed.endswith("." + base)


class RecruiterDiscoveryService:
    def __init__(
        self,
        *,
        candidate_repo: CandidateRepository,
        job_repo: JobRepository,
        company_repo: CompanyRepository,
        contact_repo: RecruiterContactRepository,
        source_repo: ContactSourceRepository,
        audit_repo: AuditRepository,
        actor_id: UUID,
        candidate_id: UUID,
        scorer: AffiliationConfidenceScorer | None = None,
        directory_fetcher: RecruiterDirectoryFetcher | None = None,
    ) -> None:
        self._candidates = candidate_repo
        self._jobs = job_repo
        self._companies = company_repo
        self._contacts = contact_repo
        self._sources = source_repo
        self._audit = audit_repo
        self._actor_id = actor_id
        self._candidate_id = candidate_id
        self._scorer = scorer or AffiliationConfidenceScorer()
        self._fetcher = directory_fetcher or make_directory_fetcher()

    async def _ensure_owned_candidate(self) -> None:
        await self._candidates.get_for_user_or_404(self._candidate_id, self._actor_id)

    async def _get_owned_job(self, job_id: UUID) -> Job:
        job = await self._jobs.get_for_candidate(job_id, self._candidate_id)
        if job is None:
            raise NotFoundError("Job not found")
        return job

    async def discover_for_job(self, job_id: UUID) -> DiscoverySummary:
        """Run a privacy-safe discovery pass for a target job and persist results."""
        await self._ensure_owned_candidate()
        job = await self._get_owned_job(job_id)
        company = await self._companies.get(job.company_id)
        if company is None:
            raise NotFoundError("Company not found")

        people = await self._fetcher.fetch(company, job)
        contacts: list[RecruiterContact] = []
        summary = DiscoverySummary(found=len(people))
        created = 0
        existing_skipped = 0
        hidden = 0

        for person in people:
            existing = await self._contacts.get_by_profile_url(
                self._candidate_id, person.profile_url
            )
            if existing is not None:
                existing_skipped += 1
                continue

            confidence = self._scorer.score(
                role_title=person.role_title,
                on_company_domain=_on_company_domain(company.website_domain, person.company_domain),
                has_public_profile_url=bool(person.profile_url.strip()),
                email_publicly_listed=person.email_publicly_listed,
            )

            contact = await self._build_persisted_contact(
                job=job,
                company=company,
                person=person,
                source_type=ContactSourceType.DIRECTORY,
                source_url=company.careers_url or job.url,
                confidence=confidence.score,
                contact_type=confidence.contact_type,
                suppressed=not confidence.surfaced,
                reasons=confidence.reasons,
                source_title=f"Public directory evidence for {company.name}",
                source_note=None,
            )
            contacts.append(contact)
            if confidence.surfaced:
                created += 1
            else:
                hidden += 1

            await self._audit.log(
                "recruiter_contact.evaluated",
                actor_id=self._actor_id,
                candidate_id=self._candidate_id,
                entity_type="RecruiterContact",
                entity_id=contact.id,
                metadata={
                    "job_id": str(job.id),
                    "company_id": str(company.id),
                    "contact_type": confidence.contact_type.value,
                    "score": confidence.score,
                    "surfaced": confidence.surfaced,
                    "email_guessed_blocked": not person.email_publicly_listed,
                    "reasons": confidence.reasons,
                },
            )

        summary.created = created
        summary.existing_skipped = existing_skipped
        summary.hidden = hidden
        summary.contacts = contacts
        await self._audit.log(
            "recruiter_contacts.discovered",
            actor_id=self._actor_id,
            candidate_id=self._candidate_id,
            entity_type="ContactSource",
            entity_id=None,
            metadata={
                "job_id": str(job.id),
                "company_id": str(company.id),
                "found": summary.found,
                "created": summary.created,
                "existing_skipped": summary.existing_skipped,
                "hidden": summary.hidden,
            },
        )
        return summary

    async def _build_persisted_contact(
        self,
        *,
        job: Job,
        company: Company,
        person: DirectoryPerson,
        source_type: ContactSourceType,
        source_url: str,
        confidence: int,
        contact_type: ContactType,
        suppressed: bool,
        reasons: list[str],
        source_title: str,
        source_note: str | None,
    ) -> RecruiterContact:
        source = await self._sources.create(
            candidate_id=self._candidate_id,
            company_id=company.id,
            source_type=source_type,
            url=source_url,
            title=source_title,
            note=source_note,
            discovered_at=datetime.now(UTC),
        )
        email = person.email if person.email_publicly_listed else None
        return await self._contacts.create(
            candidate_id=self._candidate_id,
            company_id=company.id,
            job_id=job.id,
            source_id=source.id,
            full_name=person.full_name.strip(),
            role_title=person.role_title.strip(),
            public_profile_url=person.profile_url.strip(),
            email=email,
            confidence_score=confidence,
            contact_type=contact_type,
            is_suppressed=suppressed,
            verification_details={
                "reasons": reasons,
                "source_type": source_type.value,
                "source_url": source_url,
                "email_publicly_listed": bool(email),
            },
        )

    async def list_contacts(
        self,
        *,
        company_id: UUID | None = None,
        job_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[RecruiterContact], int]:
        """List surfaced (VERIFIED, unsuppressed) contacts only."""
        await self._ensure_owned_candidate()
        items = await self._contacts.list_for_candidate(
            self._candidate_id,
            company_id=company_id,
            job_id=job_id,
            surfaced_only=True,
            limit=limit,
            offset=offset,
        )
        total = await self._contacts.count_for_candidate(
            self._candidate_id,
            company_id=company_id,
            job_id=job_id,
            surfaced_only=True,
        )
        return items, total

    async def get_contact(self, contact_id: UUID) -> RecruiterContact:
        await self._ensure_owned_candidate()
        contact = await self._contacts.get_for_candidate(contact_id, self._candidate_id)
        if contact is None:
            raise NotFoundError("Recruiter contact not found")
        return contact
