"""CP20 outreach preparation from approved recruiter signals.

Turns an APPROVED (human-reviewed) ``RECRUITER_OUTREACH_CANDIDATE`` signal into
a deterministic, fact-grounded outreach draft using the same writer and
grounding guard as the existing outreach engine. The service:

* requires candidate ownership and an approved human review
  (``recruiter_signal_review``) of the exact signal --- preparation is the first
  downstream step allowed to touch the signal, and only after a human decision,
* requires a usable verified contact and a verified destination,
* generates and re-validates a grounded draft (nothing fabricated is returned),
* pins the exact signal/evidence linkage (signal identity, evidence reference,
  generation version, approval id) onto the artifact,
* mirrors everything to the append-only audit log.

It never persists a message, never sends, never schedules, and never reaches
the network. Persisting the resulting draft into ``OutreachMessage`` remains the
outreach engine's job (see the CP23 end-to-end flow).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from backend.core.exceptions import NotFoundError, ValidationError
from backend.models.approval import Approval
from backend.models.candidate import CandidateSkill, Certification, Education, Experience
from backend.models.company import Company
from backend.models.job import Job
from backend.models.outreach import OutreachChannel
from backend.models.recruiter_contact import ContactType, RecruiterContact
from backend.models.recruiter_signal import (
    RecruiterSignal,
    RecruiterSignalStatus,
    RecruiterSignalType,
)
from backend.repositories.audit import AuditRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.certification import CertificationRepository
from backend.repositories.company import CompanyRepository
from backend.repositories.education import EducationRepository
from backend.repositories.experience import ExperienceRepository
from backend.repositories.job import JobRepository
from backend.repositories.job_match import JobMatchRepository
from backend.repositories.recruiter_contact import RecruiterContactRepository
from backend.repositories.recruiter_signal import RecruiterSignalRepository
from backend.repositories.skill import SkillRepository
from backend.schemas.recruiter_signal_outreach_prep import (
    RECRUITER_SIGNAL_OUTREACH_PREP_VERSION,
    RecruiterSignalLinkage,
    RecruiterSignalOutreachPreparation,
)
from backend.services.application_prep import ProfileFacts
from backend.services.outreach_writer import (
    DeterministicOutreachWriter,
    OutreachWriter,
)
from backend.services.recruiter_signal_approval import RecruiterSignalApprovalService

_SIGNAL_LINK_KIND = "recruiter_signal"


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class RecruiterSignalOutreachPrepService:
    """Prepare grounded outreach drafts from approved signals (never sends)."""

    def __init__(
        self,
        *,
        candidate_repo: CandidateRepository,
        signal_repo: RecruiterSignalRepository,
        contact_repo: RecruiterContactRepository,
        job_repo: JobRepository,
        company_repo: CompanyRepository,
        skill_repo: SkillRepository,
        experience_repo: ExperienceRepository,
        education_repo: EducationRepository,
        certification_repo: CertificationRepository,
        match_repo: JobMatchRepository,
        audit_repo: AuditRepository,
        approval_service: RecruiterSignalApprovalService,
        writer: OutreachWriter | None = None,
    ) -> None:
        self._candidates = candidate_repo
        self._signals = signal_repo
        self._contacts = contact_repo
        self._jobs = job_repo
        self._companies = company_repo
        self._skills = skill_repo
        self._experiences = experience_repo
        self._educations = education_repo
        self._certifications = certification_repo
        self._matches = match_repo
        self._audit = audit_repo
        self._approvals = approval_service
        self._writer = writer or DeterministicOutreachWriter()

    async def prepare(
        self,
        candidate_id: UUID,
        user_id: UUID,
        signal_id: UUID,
        *,
        channel: OutreachChannel = OutreachChannel.EMAIL,
    ) -> RecruiterSignalOutreachPreparation:
        """Prepare a grounded, draft-ready artifact from an approved signal."""
        await self._candidates.get_for_user_or_404(candidate_id, user_id)
        signal = await self._signals.get_for_candidate(signal_id, candidate_id)
        if signal is None:
            raise NotFoundError("Recruiter signal not found")
        if signal.signal_type is not RecruiterSignalType.RECRUITER_OUTREACH_CANDIDATE:
            raise ValidationError(
                f"Only RECRUITER_OUTREACH_CANDIDATE signals can be prepared; "
                f"signal is {signal.signal_type.value}"
            )
        if signal.status is not RecruiterSignalStatus.APPROVED:
            raise ValidationError(
                f"Only approved (human-reviewed) signals can be prepared; "
                f"signal is {signal.status.value}"
            )
        approval = await self._approvals.require_approved_review(
            candidate_id, user_id, signal.id
        )

        if signal.recruiter_contact_id is None:
            raise ValidationError("Signal does not reference a recruiter contact")
        contact = await self._contacts.get_for_candidate(
            signal.recruiter_contact_id, candidate_id
        )
        if contact is None:
            raise NotFoundError("Recruiter contact not found for signal")
        self._require_usable_contact(contact)
        self._require_verified_destination(contact, channel)

        job = await self._jobs.get_for_candidate(signal.job_id, candidate_id)
        if job is None:
            raise NotFoundError("Job not found")
        company = await self._companies.get(job.company_id) if job.company_id else None

        facts = await self._load_facts(candidate_id, contact, job, company)
        generated = await self._writer.generate(facts, contact, channel=channel)
        unsupported = await self._writer.validate(generated, facts, contact)
        if unsupported:
            raise ValidationError(
                "Prepared draft contains unsupported claims: " + "; ".join(unsupported)
            )

        linkage = self._linkage(signal, approval)
        prep_id = hashlib.sha256(
            _canonical_json(
                {
                    "candidate_id": str(candidate_id),
                    "signal_id": str(signal.id),
                    "signal_identity": signal.signal_identity,
                    "evidence_reference": linkage.evidence_reference,
                    "channel": channel.value,
                    "subject": generated.subject,
                    "body": generated.body,
                    "rules_version": self._writer.rules_version,
                }
            ).encode("utf-8")
        ).hexdigest()

        fact_sources = [source.to_dict() for source in generated.fact_sources]
        fact_sources.append(
            {
                "kind": _SIGNAL_LINK_KIND,
                "ref_id": str(signal.id),
                "text": signal.signal_identity,
            }
        )
        fact_sources = sorted(
            fact_sources,
            key=lambda source: (
                str(source.get("kind") or ""),
                str(source.get("ref_id") or ""),
                str(source.get("text") or ""),
            ),
        )

        preparation = RecruiterSignalOutreachPreparation(
            candidate_id=candidate_id,
            signal_id=signal.id,
            contact_id=contact.id,
            job_id=job.id,
            company_id=company.id if company else None,
            channel=channel,
            subject=generated.subject,
            body=generated.body,
            rules_version=self._writer.rules_version,
            fact_sources=fact_sources,
            prep_id=prep_id,
            linkage=linkage,
            generated_at=datetime.now(UTC),
        )

        await self._audit.log(
            event_type="RECRUITER_SIGNAL_OUTREACH_PREPARED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="RecruiterSignal",
            entity_id=signal.id,
            metadata={
                "prep_version": RECRUITER_SIGNAL_OUTREACH_PREP_VERSION,
                "prep_id": prep_id,
                "approval_id": str(linkage.approval_id),
                "evidence_reference": linkage.evidence_reference,
                "channel": channel.value,
                "rules_version": self._writer.rules_version,
                "contact_id": str(contact.id),
                "job_id": str(job.id),
            },
        )
        return preparation

    # ------------------------------------------------------------------ #
    # Gates (mirror the outreach engine's verified-contact rules)
    # ------------------------------------------------------------------ #

    def _require_usable_contact(self, contact: RecruiterContact) -> None:
        if contact.is_suppressed:
            raise ValidationError("This contact is suppressed and cannot be contacted")
        if contact.contact_type != ContactType.VERIFIED or contact.confidence_score < 70:
            raise ValidationError("Only verified recruiter contacts can be contacted")

    def _require_verified_destination(
        self, contact: RecruiterContact, channel: OutreachChannel
    ) -> None:
        if channel == OutreachChannel.EMAIL and not (contact.email or "").strip():
            raise ValidationError(
                "This contact has no verified email address; it cannot be emailed"
            )

    async def _load_facts(
        self,
        candidate_id: UUID,
        contact: RecruiterContact,
        job: Job | None,
        company: Company | None,
    ) -> ProfileFacts:
        candidate = await self._candidates.get(candidate_id)
        match = (
            await self._matches.get_for_job(candidate_id, job.id)
            if job is not None
            else None
        )
        if candidate is None:
            return ProfileFacts(candidate=None, match=match, job=job, company=company)
        skills = await self._skills.list_for_candidate(candidate.id)
        experiences = await self._experiences.list_ordered(candidate.id)
        educations = await self._educations.list_ordered(candidate.id)
        certifications = await self._certifications.list_ordered(candidate.id)
        return ProfileFacts(
            candidate=candidate,
            skills=[s for s in skills if isinstance(s, CandidateSkill)],
            experiences=[e for e in experiences if isinstance(e, Experience)],
            educations=[e for e in educations if isinstance(e, Education)],
            certifications=[c for c in certifications if isinstance(c, Certification)],
            match=match,
            job=job,
            company=company,
        )

    def _linkage(self, signal: RecruiterSignal, approval: Approval) -> RecruiterSignalLinkage:
        provenance = signal.provenance_json or {}
        return RecruiterSignalLinkage(
            signal_id=signal.id,
            signal_identity=signal.signal_identity,
            signal_type=signal.signal_type.value,
            evidence_reference=provenance.get("evidence_reference") or "",
            generation_version=provenance.get("generation_version"),
            signal_status=signal.status.value,
            approval_id=UUID(str(approval.id)),
        )


__all__ = [
    "RecruiterSignalOutreachPrepService",
    "RECRUITER_SIGNAL_OUTREACH_PREP_VERSION",
]
