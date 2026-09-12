"""Recruiter / professional outreach service.

Safe outreach workflow, candidate-scoped (ownership enforced at the API layer
and re-checked here). Hard invariants:

* Drafts reference only VERIFIED, unsuppressed contacts and are grounded in
  verified candidate facts + verified contact/job information (deterministic
  writer + grounding validator; nothing fabricated is ever persisted).
* Sending requires an APPROVED human approval (``Approval`` kind
  ``outreach_send``) unless ``outreach_approval_required`` is disabled, a
  verified destination, a non-suppressed contact, and respects the per-candidate
  daily send cap.
* At most one non-terminal run may exist per message and duplicate sends are
  prevented; failed retryable attempts are scheduled with exponential backoff
  capped by ``max_attempts``.
* Every transition mirrors to the append-only audit log. Guessed emails are
  never used; the email destination is only ever a publicly listed,
  source-exposed address on the verified contact.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from backend.core.exceptions import NotFoundError, ValidationError
from backend.models.approval import Approval, ApprovalKind
from backend.models.candidate import CandidateSkill, Certification, Education, Experience
from backend.models.company import Company
from backend.models.job import Job
from backend.models.job_match import JobMatch
from backend.models.outreach import (
    OutreachChannel,
    OutreachMessage,
    OutreachRun,
    OutreachRunStatus,
    OutreachStatus,
    ResponseStatus,
)
from backend.models.recruiter_contact import ContactType, RecruiterContact
from backend.repositories.application import ApplicationRepository
from backend.repositories.approval import ApprovalRepository
from backend.repositories.audit import AuditRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.certification import CertificationRepository
from backend.repositories.company import CompanyRepository
from backend.repositories.education import EducationRepository
from backend.repositories.experience import ExperienceRepository
from backend.repositories.job import JobRepository
from backend.repositories.job_match import JobMatchRepository
from backend.repositories.outreach import (
    OutreachMessageRepository,
    OutreachMessageVersionRepository,
    OutreachRunRepository,
)
from backend.repositories.recruiter_contact import RecruiterContactRepository
from backend.repositories.skill import SkillRepository
from backend.services.application_prep import ProfileFacts
from backend.services.approval import ApprovalService
from backend.services.outreach_adapter import (
    OutreachPayload,
    OutreachSender,
    SendOutcomeKind,
    make_sender,
)
from backend.services.outreach_writer import (
    DeterministicOutreachWriter,
    GeneratedOutreach,
    OutreachWriter,
)

ACTIVE_RUN_STATUSES = frozenset({OutreachRunStatus.PENDING, OutreachRunStatus.RUNNING})


class OutreachService:
    def __init__(
        self,
        *,
        candidate_repo: CandidateRepository,
        contact_repo: RecruiterContactRepository,
        job_repo: JobRepository,
        company_repo: CompanyRepository,
        skill_repo: SkillRepository,
        experience_repo: ExperienceRepository,
        education_repo: EducationRepository,
        certification_repo: CertificationRepository,
        match_repo: JobMatchRepository,
        application_repo: ApplicationRepository,
        message_repo: OutreachMessageRepository,
        version_repo: OutreachMessageVersionRepository,
        run_repo: OutreachRunRepository,
        audit_repo: AuditRepository,
        approval_repo: ApprovalRepository,
        approval_service: ApprovalService,
        actor_id: UUID,
        candidate_id: UUID,
        autonomy_level: int = 2,
        approval_required: bool = True,
        daily_limit: int = 20,
        max_attempts: int = 3,
        retry_base_seconds: int = 60,
        sender: OutreachSender | None = None,
        writer: OutreachWriter | None = None,
    ) -> None:
        self._candidates = candidate_repo
        self._contacts = contact_repo
        self._jobs = job_repo
        self._companies = company_repo
        self._skills = skill_repo
        self._experiences = experience_repo
        self._educations = education_repo
        self._certifications = certification_repo
        self._matches = match_repo
        self._applications = application_repo
        self._messages = message_repo
        self._versions = version_repo
        self._runs = run_repo
        self._audit = audit_repo
        self._approval_repo = approval_repo
        self._approvals = approval_service
        self._actor_id = actor_id
        self._candidate_id = candidate_id
        self._autonomy_level = autonomy_level
        self._approval_required = approval_required
        self._daily_limit = daily_limit
        self._max_attempts = max_attempts
        self._retry_base_seconds = retry_base_seconds
        self._sender = sender or make_sender()
        self._writer = writer or DeterministicOutreachWriter()

    # ------------------------------------------------------------- ownership

    async def _ensure_owned_candidate(self) -> None:
        await self._candidates.get_for_user_or_404(self._candidate_id, self._actor_id)

    async def _get_owned_contact(self, contact_id: UUID) -> RecruiterContact:
        contact = await self._contacts.get_for_candidate(contact_id, self._candidate_id)
        if contact is None:
            raise NotFoundError("Recruiter contact not found")
        return contact

    def _require_usable_contact(self, contact: RecruiterContact) -> None:
        if contact.is_suppressed:
            raise ValidationError("This contact is suppressed and cannot be contacted")
        if contact.contact_type != ContactType.VERIFIED or contact.confidence_score < 70:
            raise ValidationError("Only verified recruiter contacts can be contacted")

    async def _get_owned_message(self, message_id: UUID) -> OutreachMessage:
        message = await self._messages.get_for_candidate(message_id, self._candidate_id)
        if message is None:
            raise NotFoundError("Outreach message not found")
        return message

    async def _get_owned_run(self, run_id: UUID) -> OutreachRun:
        run = await self._runs.get_for_candidate(run_id, self._candidate_id)
        if run is None:
            raise NotFoundError("Outreach run not found")
        return run

    # ----------------------------------------------------------------- draft

    async def create_draft(
        self,
        *,
        contact_id: UUID,
        job_id: UUID | None = None,
        application_id: UUID | None = None,
        channel: OutreachChannel = OutreachChannel.EMAIL,
        subject: str | None = None,
        body: str | None = None,
    ) -> OutreachMessage:
        """Create a grounded draft for a verified contact (generated if no text)."""
        await self._ensure_owned_candidate()
        contact = await self._get_owned_contact(contact_id)
        self._require_usable_contact(contact)

        job: Job | None = None
        company: Company | None = None
        if job_id is not None:
            job = await self._jobs.get_for_candidate(job_id, self._candidate_id)
            if job is None:
                raise NotFoundError("Job not found")
            company = await self._companies.get(job.company_id)
        if application_id is not None:
            application = await self._applications.get_for_candidate(
                application_id, self._candidate_id
            )
            if application is None:
                raise NotFoundError("Application not found")

        facts = await self._load_facts(
            contact, job_id=job.id if job else None, company=company
        )
        pending = self._writer.generate(facts, contact, channel=channel)
        generated = await pending

        effective_subject = subject if subject is not None else generated.subject
        effective_body = body if body is not None else generated.body

        unsupported = await self._writer.validate(
            GeneratedOutreach(subject=effective_subject, body=effective_body),
            facts,
            contact,
        )
        if unsupported:
            raise ValidationError(
                "Draft contains unsupported claims: " + "; ".join(unsupported)
            )

        message = await self._messages.create(
            candidate_id=self._candidate_id,
            contact_id=contact.id,
            job_id=job_id,
            application_id=application_id,
            channel=channel,
            subject=effective_subject,
            body=effective_body,
            status=OutreachStatus.DRAFT,
            response_status=ResponseStatus.NO_RESPONSE,
            is_follow_up=False,
            rules_version=self._writer.rules_version,
            fact_sources=[f.to_dict() for f in generated.fact_sources],
        )
        await self._versions.create(
            message_id=message.id,
            version_number=1,
            subject=effective_subject,
            body=effective_body,
            is_generated=subject is None and body is None,
            fact_sources=[f.to_dict() for f in generated.fact_sources],
            created_by=str(self._actor_id),
        )
        await self._audit.log(
            "outreach.drafted",
            actor_id=self._actor_id,
            candidate_id=self._candidate_id,
            entity_type="outreach_message",
            entity_id=message.id,
            metadata={
                "contact_id": str(contact.id),
                "job_id": str(job_id) if job_id else None,
                "channel": channel.value,
                "generated": subject is None and body is None,
            },
        )
        return message

    async def create_follow_up(
        self,
        *,
        parent_message_id: UUID,
        subject: str | None = None,
        body: str | None = None,
    ) -> OutreachMessage:
        """Create a follow-up draft for an already-sent outreach message."""
        await self._ensure_owned_candidate()
        parent = await self._get_owned_message(parent_message_id)
        if parent.status != OutreachStatus.SENT:
            raise ValidationError(
                "A follow-up can only be drafted after the original message was sent"
            )
        contact = await self._get_owned_contact(parent.contact_id)
        self._require_usable_contact(contact)
        facts = await self._load_facts(
            contact, job_id=parent.job_id, company=None
        )

        pending = self._writer.generate_follow_up(
            facts, contact, parent_subject=parent.subject, channel=parent.channel
        )
        generated = await pending
        effective_subject = subject if subject is not None else generated.subject
        effective_body = body if body is not None else generated.body
        unsupported = await self._writer.validate(
            GeneratedOutreach(subject=effective_subject, body=effective_body),
            facts,
            contact,
        )
        if unsupported:
            raise ValidationError(
                "Draft contains unsupported claims: " + "; ".join(unsupported)
            )

        message = await self._messages.create(
            candidate_id=self._candidate_id,
            contact_id=contact.id,
            job_id=parent.job_id,
            application_id=parent.application_id,
            channel=parent.channel,
            subject=effective_subject,
            body=effective_body,
            status=OutreachStatus.DRAFT,
            response_status=ResponseStatus.NO_RESPONSE,
            is_follow_up=True,
            parent_id=parent.id,
            rules_version=self._writer.rules_version,
            fact_sources=[f.to_dict() for f in generated.fact_sources],
        )
        await self._versions.create(
            message_id=message.id,
            version_number=1,
            subject=effective_subject,
            body=effective_body,
            is_generated=subject is None and body is None,
            fact_sources=[f.to_dict() for f in generated.fact_sources],
            created_by=str(self._actor_id),
        )
        await self._audit.log(
            "outreach.follow_up_drafted",
            actor_id=self._actor_id,
            candidate_id=self._candidate_id,
            entity_type="outreach_message",
            entity_id=message.id,
            metadata={"parent_id": str(parent.id)},
        )
        return message

    # ------------------------------------------------------------------ reads

    async def get_message(self, message_id: UUID) -> OutreachMessage:
        await self._ensure_owned_candidate()
        return await self._get_owned_message(message_id)

    async def get_message_detail(self, message_id: UUID) -> OutreachMessage:
        await self._ensure_owned_candidate()
        message = await self._messages.get_for_candidate_detailed(
            message_id, self._candidate_id
        )
        if message is None:
            raise NotFoundError("Outreach message not found")
        return message

    async def list_messages(
        self,
        *,
        contact_id: UUID | None = None,
        job_id: UUID | None = None,
        status: OutreachStatus | None = None,
        channel: OutreachChannel | None = None,
        is_follow_up: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[OutreachMessage], int]:
        await self._ensure_owned_candidate()
        items = await self._messages.list_for_candidate(
            self._candidate_id,
            contact_id=contact_id,
            job_id=job_id,
            status=status,
            channel=channel,
            is_follow_up=is_follow_up,
            limit=limit,
            offset=offset,
        )
        total = await self._messages.count_for_candidate(
            self._candidate_id, status=status, channel=channel
        )
        return items, total

    # ---------------------------------------------------------------- editing

    async def update_draft(
        self,
        message_id: UUID,
        *,
        subject: str,
        body: str,
        change_reason: str | None = None,
    ) -> OutreachMessage:
        """Apply a human edit to a draft. Every edit appends a version row."""
        await self._ensure_owned_candidate()
        message = await self._get_owned_message(message_id)
        if message.status != OutreachStatus.DRAFT:
            raise ValidationError(
                f"Cannot edit a message that is {message.status.value}; "
                "only drafts can be edited"
            )
        contact = await self._get_owned_contact(message.contact_id)
        facts = await self._load_facts(contact, job_id=message.job_id, company=None)

        version_number = await self._versions.next_version_number(message.id)
        await self._versions.create(
            message_id=message.id,
            version_number=version_number,
            subject=subject,
            body=body,
            is_generated=False,
            change_reason=change_reason,
            fact_sources=[f.to_dict() for f in facts.entities()],
            created_by=str(self._actor_id),
        )
        message = await self._messages.update(message, subject=subject, body=body)
        await self._audit.log(
            "outreach.updated",
            actor_id=self._actor_id,
            candidate_id=self._candidate_id,
            entity_type="outreach_message",
            entity_id=message.id,
            metadata={"version": version_number, "change_reason": change_reason},
        )
        return message

    # ------------------------------------------------------------------ approval

    async def submit_for_approval(
        self,
        message_id: UUID,
        *,
        summary: str | None = None,
    ) -> Approval | None:
        """Submit a draft for human approval (or mark approved if not required).

        Returns the created (or existing) ``Approval`` when approval is required,
        otherwise ``None`` (the message is directly APPROVED).
        """
        await self._ensure_owned_candidate()
        message = await self._get_owned_message(message_id)
        contact = await self._get_owned_contact(message.contact_id)

        if message.status == OutreachStatus.APPROVED:
            approved = await self._approval_repo.get_approved_for_target(
                self._candidate_id,
                ApprovalKind.OUTREACH_SEND,
                "outreach_message",
                message.id,
            )
            return approved if approved is not None else None
        if message.status == OutreachStatus.PENDING_APPROVAL:
            return await self._approval_repo.get_open_for_target(
                self._candidate_id,
                ApprovalKind.OUTREACH_SEND,
                "outreach_message",
                message.id,
            )
        if message.status != OutreachStatus.DRAFT:
            raise ValidationError(
                f"Cannot submit a message that is {message.status.value} for approval"
            )

        approval: Approval | None = None
        if self._approval_required:
            context: dict[str, object] = {
                "contact": contact.full_name,
                "role_title": contact.role_title,
                "channel": message.channel.value,
                "subject": message.subject,
                "job_id": str(message.job_id) if message.job_id else None,
                "destination_verified": bool(
                    message.channel == OutreachChannel.EMAIL and contact.email
                ),
            }
            approval = await self._approvals.request_approval(
                kind=ApprovalKind.OUTREACH_SEND,
                target_type="outreach_message",
                target_id=message.id,
                summary=summary or f"Send outreach to {contact.full_name}",
                context=context,
            )
            message = await self._messages.update(
                message,
                status=OutreachStatus.PENDING_APPROVAL,
                approval_id=str(approval.id),
            )
        else:
            message = await self._messages.update(
                message, status=OutreachStatus.APPROVED
            )
        await self._audit.log(
            "outreach.submitted_for_approval",
            actor_id=self._actor_id,
            candidate_id=self._candidate_id,
            entity_type="outreach_message",
            entity_id=message.id,
            metadata={
                "approval_id": str(approval.id) if approval else None,
                "approval_required": self._approval_required,
            },
        )
        return approval

    async def cancel(self, message_id: UUID) -> OutreachMessage:
        """Cancel a draft/pending/approved message."""
        await self._ensure_owned_candidate()
        message = await self._get_owned_message(message_id)
        if message.status in (OutreachStatus.SENT, OutreachStatus.CANCELLED):
            raise ValidationError(
                f"Cannot cancel a message that is {message.status.value}"
            )
        message = await self._messages.update(
            message, status=OutreachStatus.CANCELLED
        )
        await self._audit.log(
            "outreach.cancelled",
            actor_id=self._actor_id,
            candidate_id=self._candidate_id,
            entity_type="outreach_message",
            entity_id=message.id,
            metadata={"status": message.status.value},
        )
        return message

    # ------------------------------------------------------------------- send

    async def send(self, message_id: UUID) -> OutreachRun:
        """Start (and run) the send workflow for an approved message."""
        await self._ensure_owned_candidate()
        if self._autonomy_level < 2:
            raise ValidationError(
                "Autonomy level does not permit automated outreach sending"
            )

        message = await self._get_owned_message(message_id)
        contact = await self._get_owned_contact(message.contact_id)
        self._require_usable_contact(contact)

        if message.status not in (
            OutreachStatus.PENDING_APPROVAL,
            OutreachStatus.APPROVED,
            OutreachStatus.FAILED,
        ):
            raise ValidationError(
                f"Cannot send a message that is {message.status.value}"
            )

        approved_approval = None
        if self._approval_required:
            approved_approval = await self._approval_repo.get_approved_for_target(
                self._candidate_id,
                ApprovalKind.OUTREACH_SEND,
                "outreach_message",
                message.id,
            )
            if approved_approval is None:
                pending = await self._approval_repo.get_open_for_target(
                    self._candidate_id,
                    ApprovalKind.OUTREACH_SEND,
                    "outreach_message",
                    message.id,
                )
                if pending is not None:
                    raise ValidationError(
                        "Approval is still pending; a human decision is required before sending"
                    )
                raise ValidationError(
                    "No approved approval exists for this message; it cannot be sent automatically"
                )
        elif message.status == OutreachStatus.PENDING_APPROVAL:
            raise ValidationError(
                "Approval is not required but the message was never approved"
            )

        if message.status == OutreachStatus.PENDING_APPROVAL:
            message = await self._messages.update(
                message, status=OutreachStatus.APPROVED
            )
            await self._audit.log(
                "outreach.approved",
                actor_id=self._actor_id,
                candidate_id=self._candidate_id,
                entity_type="outreach_message",
                entity_id=message.id,
                metadata={
                    "approval_id": str(approved_approval.id)
                    if approved_approval
                    else None
                },
            )

        self._require_verified_destination(message, contact)
        await self._enforce_daily_limit()

        latest = await self._runs.get_for_message(message.id)
        if latest is not None:
            if latest.status in ACTIVE_RUN_STATUSES:
                raise ValidationError(
                    f"A run is already {latest.status.value} for this message"
                )
            if latest.status == OutreachRunStatus.FAILED and latest.next_retry_at is not None:
                raise ValidationError(
                    "A failed run is still retry-pending; retry it instead of starting a new run"
                )

        job = await self._jobs.get_for_candidate(message.job_id, self._candidate_id) if message.job_id else None
        company = await self._companies.get(job.company_id) if job else None
        run = await self._runs.create(
            candidate_id=self._candidate_id,
            message_id=message.id,
            status=OutreachRunStatus.RUNNING,
            attempt_count=0,
            max_attempts=self._max_attempts,
            started_at=datetime.now(UTC),
            result_metadata={
                "contact_id": str(contact.id),
                "approval_id": str(approved_approval.id)
                if approved_approval
                else None,
                "company": company.name if company else (job.title if job else None),
            },
        )
        await self._audit.log(
            "outreach.run_started",
            actor_id=self._actor_id,
            candidate_id=self._candidate_id,
            entity_type="outreach_run",
            entity_id=run.id,
            metadata={
                "message_id": str(message.id),
                "channel": message.channel.value,
                "approval_required": self._approval_required,
            },
        )
        return await self._attempt(run, message, contact, job, company)

    async def retry(self, run_id: UUID) -> OutreachRun:
        """Retry a failed (retry-pending) outreach run."""
        run = await self._get_owned_run(run_id)
        await self._ensure_owned_candidate()

        if run.status == OutreachRunStatus.SENT:
            raise ValidationError("This run already sent the message")
        if run.status != OutreachRunStatus.FAILED:
            raise ValidationError(f"Cannot retry a run that is {run.status.value}")
        if run.next_retry_at is None:
            raise ValidationError("This run is not retryable; start a new send instead")
        if run.attempt_count >= run.max_attempts:
            raise ValidationError("Maximum retry attempts reached; start a new send instead")

        message = await self._get_owned_message(run.message_id)
        if message.status != OutreachStatus.FAILED:
            raise ValidationError(
                "The message is not marked failed; retry is not permitted"
            )
        contact = await self._get_owned_contact(message.contact_id)
        self._require_usable_contact(contact)
        if self._approval_required:
            approved = await self._approval_repo.get_approved_for_target(
                self._candidate_id,
                ApprovalKind.OUTREACH_SEND,
                "outreach_message",
                message.id,
            )
            if approved is None:
                raise ValidationError(
                    "No approved approval exists for this message; it cannot be sent automatically"
                )
        self._require_verified_destination(message, contact)
        await self._enforce_daily_limit()

        job = await self._jobs.get_for_candidate(message.job_id, self._candidate_id) if message.job_id else None
        company = await self._companies.get(job.company_id) if job else None
        run = await self._runs.update(
            run,
            status=OutreachRunStatus.RUNNING,
            next_retry_at=None,
            last_error=None,
            result_metadata={
                **(run.result_metadata or {}),
                "retried_at": datetime.now(UTC).isoformat(),
            },
        )
        await self._audit.log(
            "outreach.run_retried",
            actor_id=self._actor_id,
            candidate_id=self._candidate_id,
            entity_type="outreach_run",
            entity_id=run.id,
            metadata={"message_id": str(message.id), "attempt": run.attempt_count + 1},
        )
        return await self._attempt(run, message, contact, job, company)

    # ------------------------------------------------------------ responses / suppression

    async def record_response(
        self,
        message_id: UUID,
        *,
        note: str | None = None,
    ) -> OutreachMessage:
        """Record that the recipient responded to a sent message."""
        await self._ensure_owned_candidate()
        message = await self._get_owned_message(message_id)
        if message.status != OutreachStatus.SENT:
            raise ValidationError(
                f"Cannot record a response for a message that is {message.status.value}"
            )
        message = await self._messages.update(
            message,
            response_status=ResponseStatus.RESPONDED,
            responded_at=datetime.now(UTC),
        )
        await self._audit.log(
            "outreach.response_recorded",
            actor_id=self._actor_id,
            candidate_id=self._candidate_id,
            entity_type="outreach_message",
            entity_id=message.id,
            metadata={"note": note} if note else None,
        )
        return message

    async def mark_suppressed(
        self,
        message_id: UUID,
        *,
        reason: str,
    ) -> OutreachMessage:
        """Suppress the underlying contact after a bounce/opt-out."""
        await self._ensure_owned_candidate()
        message = await self._get_owned_message(message_id)
        contact = await self._get_owned_contact(message.contact_id)
        contact = await self._contacts.update(contact, is_suppressed=True)
        await self._audit.log(
            "outreach.suppressed",
            actor_id=self._actor_id,
            candidate_id=self._candidate_id,
            entity_type="outreach_message",
            entity_id=message.id,
            metadata={
                "contact_id": str(contact.id),
                "reason": reason,
                "message_status": message.status.value,
            },
        )
        return message

    # ------------------------------------------------------------------- runs

    async def list_runs(
        self,
        *,
        status: OutreachRunStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[OutreachRun], int]:
        await self._ensure_owned_candidate()
        items = await self._runs.list_for_candidate(
            self._candidate_id, status=status, limit=limit, offset=offset
        )
        total = await self._runs.count_for_candidate(self._candidate_id, status=status)
        return items, total

    async def get_run(self, run_id: UUID) -> OutreachRun:
        await self._ensure_owned_candidate()
        return await self._get_owned_run(run_id)

    async def summary(self) -> dict[str, int]:
        await self._ensure_owned_candidate()
        counts = await self._messages.count_by_status(self._candidate_id)
        sent_today = await self._count_sent_today()
        responded = await self._messages.count_responded(self._candidate_id)
        return {
            "total": await self._messages.count_for_candidate(self._candidate_id),
            "draft": counts.get(OutreachStatus.DRAFT, 0),
            "pending_approval": counts.get(OutreachStatus.PENDING_APPROVAL, 0),
            "approved": counts.get(OutreachStatus.APPROVED, 0),
            "sent": counts.get(OutreachStatus.SENT, 0),
            "failed": counts.get(OutreachStatus.FAILED, 0),
            "cancelled": counts.get(OutreachStatus.CANCELLED, 0),
            "responded": responded,
            "sent_today": sent_today,
            "daily_limit": self._daily_limit,
        }

    # ------------------------------------------------------------------ helpers

    def _require_verified_destination(
        self, message: OutreachMessage, contact: RecruiterContact
    ) -> None:
        if message.channel == OutreachChannel.EMAIL:
            if not contact.email:
                raise ValidationError(
                    "This contact has no verified email address; it cannot be emailed"
                )
        elif (
            message.channel == OutreachChannel.PROFESSIONAL_NETWORK
            and not contact.public_profile_url
        ):
            raise ValidationError(
                "This contact has no verified profile link; it cannot be messaged"
            )

    async def _enforce_daily_limit(self) -> None:
        sent_today = await self._count_sent_today()
        if sent_today >= self._daily_limit:
            raise ValidationError(
                f"Daily outreach send limit of {self._daily_limit} reached "
                f"({sent_today} already sent today)"
            )

    async def _count_sent_today(self) -> int:
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        return await self._messages.count_sent_since(self._candidate_id, start)

    async def _load_facts(
        self,
        contact: RecruiterContact,
        *,
        job_id: UUID | None,
        company: Company | None,
    ) -> ProfileFacts:
        candidate = await self._candidates.get(self._candidate_id)
        job: Job | None = None
        match: JobMatch | None = None
        if job_id is not None:
            job = await self._jobs.get_for_candidate(job_id, self._candidate_id)
            if job is not None:
                match = await self._matches.get_for_job(self._candidate_id, job_id)
                company = company or await self._companies.get(job.company_id)
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

    async def _attempt(
        self,
        run: OutreachRun,
        message: OutreachMessage,
        contact: RecruiterContact,
        job: Job | None,
        company: Company | None,
    ) -> OutreachRun:
        company_name = company.name if company else ""
        job_title = job.title if job else ""
        to_address = (
            contact.email
            if message.channel == OutreachChannel.EMAIL
            else contact.public_profile_url
        )
        payload = OutreachPayload(
            message_id=message.id,
            to_address=to_address or "",
            subject=message.subject,
            body=message.body,
            contact_name=contact.full_name,
            company_name=company_name,
            job_title=job_title,
            channel=message.channel,
        )
        outcome = await self._sender.send(payload)
        now = datetime.now(UTC)

        if outcome.kind == SendOutcomeKind.SENT:
            run = await self._runs.update(
                run,
                status=OutreachRunStatus.SENT,
                sent_at=now,
                finished_at=now,
                last_error=None,
                provider_message_id=outcome.provider_message_id,
                result_metadata={
                    **(outcome.details or {}),
                    "message": outcome.message,
                },
            )
            message = await self._messages.update(
                message,
                status=OutreachStatus.SENT,
                sent_at=now,
                last_error=None,
                provider_message_id=outcome.provider_message_id,
            )
            await self._audit.log(
                "outreach.sent",
                actor_id=self._actor_id,
                candidate_id=self._candidate_id,
                entity_type="outreach_message",
                entity_id=message.id,
                metadata={
                    "run_id": str(run.id),
                    "channel": message.channel.value,
                    "provider_message_id": outcome.provider_message_id,
                },
            )
            return run

        attempts_used = run.attempt_count + 1
        exhausted = attempts_used >= run.max_attempts
        next_retry_at = (
            None
            if not outcome.retryable or exhausted
            else now + timedelta(seconds=self._retry_base_seconds * (2 ** max(attempts_used - 1, 0)))
        )
        run = await self._runs.update(
            run,
            status=OutreachRunStatus.FAILED,
            attempt_count=attempts_used,
            next_retry_at=next_retry_at,
            last_error=outcome.message or "Outreach send failed",
            finished_at=now,
            result_metadata={
                **(run.result_metadata or {}),
                "failure": outcome.message,
                "retryable": outcome.retryable,
            },
        )
        message = await self._messages.update(
            message,
            status=OutreachStatus.FAILED,
            last_error=outcome.message or "Outreach send failed",
        )
        await self._audit.log(
            "outreach.send_failed",
            actor_id=self._actor_id,
            candidate_id=self._candidate_id,
            entity_type="outreach_run",
            entity_id=run.id,
            result="failed",
            metadata={
                "message_id": str(message.id),
                "attempt": attempts_used,
                "max_attempts": run.max_attempts,
                "exhausted": exhausted,
            },
            details=outcome.message,
        )
        return run
