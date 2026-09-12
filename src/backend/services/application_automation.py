"""Permitted application automation service.

Safety invariants (enforced in the service, not just the API layer):

* An application is only executed when its job source *explicitly* permits
  automation (``JobSource.terms_allow_automation``).
* An APPROVED human approval for exactly this application is required before any
  execution (roadmap acceptance: "prepared application cannot proceed without
  approval"). A still-pending or rejected approval blocks execution.
* At most one non-terminal run may exist per application; executing an already
  submitted/withdrawn application is rejected.
* A challenge detected on the site (CAPTCHA/MFA/bot protection/login) pauses the
  run and hands off to the Phase 1.5 human-in-the-loop machinery. There is never
  any attempt to solve or bypass such a challenge.
* Failed retryable attempts are scheduled with exponential backoff and capped by
  ``max_attempts`` (no endless retry loop).
* Every transition is mirrored to the append-only audit log.

Real browser/API ATS adapters plug in behind :class:`ApplicationSubmitter` and
must keep these invariants; the default submitter only records the submission.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from backend.core.exceptions import NotFoundError, ValidationError
from backend.models.application import Application, ApplicationStatus
from backend.models.approval import Approval, ApprovalKind
from backend.models.authentication import (
    AuthenticationMethod,
    AuthProvider,
    AuthProviderType,
)
from backend.models.automation_run import AutomationRun, AutomationRunStatus
from backend.models.challenge import ChallengeSeverity, ChallengeStatus, ChallengeType
from backend.models.company import Company
from backend.models.job import Job
from backend.repositories.application import (
    ApplicationDocumentRepository,
    ApplicationRepository,
)
from backend.repositories.approval import ApprovalRepository
from backend.repositories.audit import AuditRepository
from backend.repositories.automation_run import AutomationRunRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.challenge import ChallengeRepository
from backend.repositories.company import CompanyRepository
from backend.repositories.job import JobRepository
from backend.repositories.job_source import JobSourceRepository
from backend.services.authentication_provider import AuthProviderService
from backend.services.automation_adapter import (
    ApplicationSubmitter,
    SubmissionPayload,
    SubmitOutcome,
    SubmitOutcomeKind,
    make_submitter,
)
from backend.services.challenge import ChallengeService

ACTIVE_RUN_STATUSES = frozenset(
    {
        AutomationRunStatus.PENDING,
        AutomationRunStatus.RUNNING,
        AutomationRunStatus.PAUSED_HUMAN_ACTION,
    }
)
TERMINAL_RUN_STATUSES = frozenset(
    {AutomationRunStatus.SUBMITTED, AutomationRunStatus.FAILED, AutomationRunStatus.CANCELLED}
)

_TRANSITIONS: dict[AutomationRunStatus, frozenset[AutomationRunStatus]] = {
    AutomationRunStatus.RUNNING: frozenset(
        {
            AutomationRunStatus.SUBMITTED,
            AutomationRunStatus.PAUSED_HUMAN_ACTION,
            AutomationRunStatus.FAILED,
        }
    ),
    AutomationRunStatus.PAUSED_HUMAN_ACTION: frozenset(
        {AutomationRunStatus.RUNNING, AutomationRunStatus.CANCELLED, AutomationRunStatus.FAILED}
    ),
    AutomationRunStatus.FAILED: frozenset({AutomationRunStatus.RUNNING}),
    AutomationRunStatus.SUBMITTED: frozenset(),
    AutomationRunStatus.CANCELLED: frozenset(),
    AutomationRunStatus.PENDING: frozenset({AutomationRunStatus.RUNNING}),
}


def domain_of(url: str | None) -> str | None:
    if not url:
        return None
    host = url.split("://")[-1].split("/")[0].lower()
    return host or None


class ApplicationAutomationService:
    def __init__(
        self,
        *,
        candidate_repo: CandidateRepository,
        job_repo: JobRepository,
        company_repo: CompanyRepository,
        job_source_repo: JobSourceRepository,
        application_repo: ApplicationRepository,
        document_repo: ApplicationDocumentRepository,
        run_repo: AutomationRunRepository,
        approval_repo: ApprovalRepository,
        audit_repo: AuditRepository,
        challenge_repo: ChallengeRepository,
        provider_service: AuthProviderService,
        challenge_service: ChallengeService,
        actor_id: UUID,
        candidate_id: UUID,
        autonomy_level: int = 2,
        automation_enabled: bool = True,
        max_attempts: int = 3,
        retry_base_seconds: int = 60,
        submitter: ApplicationSubmitter | None = None,
    ) -> None:
        self._candidates = candidate_repo
        self._jobs = job_repo
        self._companies = company_repo
        self._sources = job_source_repo
        self._applications = application_repo
        self._documents = document_repo
        self._runs = run_repo
        self._approvals = approval_repo
        self._audit = audit_repo
        self._challenges = challenge_repo
        self._providers = provider_service
        self._challenges_service = challenge_service
        self._actor_id = actor_id
        self._candidate_id = candidate_id
        self._autonomy_level = autonomy_level
        self._automation_enabled = automation_enabled
        self._max_attempts = max_attempts
        self._retry_base_seconds = retry_base_seconds
        self._submitter = submitter or make_submitter()

    # ------------------------------------------------------------- ownership

    async def _ensure_owned_candidate(self) -> None:
        await self._candidates.get_for_user_or_404(self._candidate_id, self._actor_id)

    async def _get_owned_application(self, application_id: UUID) -> Application:
        application = await self._applications.get_for_candidate(
            application_id, self._candidate_id
        )
        if application is None:
            raise NotFoundError("Application not found")
        return application

    async def _get_owned_run(self, run_id: UUID) -> AutomationRun:
        run = await self._runs.get_for_candidate(run_id, self._candidate_id)
        if run is None:
            raise NotFoundError("Automation run not found")
        return run

    # ---------------------------------------------------------------- execute

    async def execute(self, application_id: UUID) -> AutomationRun:
        """Start (and run) the permitted submission workflow for an application."""
        await self._ensure_owned_candidate()
        if not self._automation_enabled:
            raise ValidationError("Application automation is disabled by configuration")

        application = await self._get_owned_application(application_id)
        self._check_application_ready(application)

        latest = await self._runs.get_for_application(application_id)
        if latest is not None:
            if latest.status in ACTIVE_RUN_STATUSES:
                raise ValidationError(
                    f"An automation run is already {latest.status.value} for this application"
                )
            if latest.status == AutomationRunStatus.FAILED and latest.next_retry_at is not None:
                raise ValidationError(
                    "A failed run is still retry-pending; retry it instead of starting a new run"
                )

        self._check_autonomy()
        job = await self._jobs.get_for_candidate(application.job_id, self._candidate_id)
        if job is None:
            raise NotFoundError("Job not found")
        source = await self._sources.get_for_candidate(job.source_id, self._candidate_id)
        if source is None or not source.terms_allow_automation:
            raise ValidationError(
                "This job's source does not explicitly permit automated application submission"
            )
        if source is not None and not source.is_enabled:
            raise ValidationError("The job source is disabled")

        approved = await self._get_approved_approval(application)
        company = await self._companies.get(job.company_id)
        provider = await self._ensure_provider(job, company)

        run = await self._runs.create(
            candidate_id=self._candidate_id,
            application_id=application.id,
            provider_id=provider.id,
            status=AutomationRunStatus.RUNNING,
            attempt_count=0,
            max_attempts=self._max_attempts,
            context_metadata={
                "job_id": str(job.id),
                "source_id": str(source.id) if source is not None else None,
                "approval_id": str(approved.id),
                "source_permits_automation": bool(
                    source.terms_allow_automation if source is not None else False
                ),
            },
            started_at=datetime.now(UTC),
        )
        await self._audit.log(
            "automation.run_started",
            actor_id=self._actor_id,
            candidate_id=self._candidate_id,
            entity_type="automation_run",
            entity_id=run.id,
            metadata={
                "application_id": str(application.id),
                "approval_id": str(approved.id),
                "autonomy_level": self._autonomy_level,
            },
        )
        return await self._attempt(run, application, job, company, approved)

    async def retry(self, run_id: UUID) -> AutomationRun:
        """Retry a failed (retry-pending) or challenge-paused automation run."""
        run = await self._get_owned_run(run_id)
        await self._ensure_owned_candidate()

        if run.status == AutomationRunStatus.SUBMITTED:
            raise ValidationError("This run already submitted the application")
        if run.status in (AutomationRunStatus.PENDING, AutomationRunStatus.RUNNING):
            raise ValidationError(f"Cannot retry a run that is {run.status}")
        if run.status == AutomationRunStatus.CANCELLED:
            raise ValidationError("This run was cancelled; start a new run instead")
        if run.attempt_count >= run.max_attempts:
            raise ValidationError(
                "Maximum retry attempts reached; start a new run instead"
            )
        if run.status == AutomationRunStatus.FAILED and run.next_retry_at is None:
            raise ValidationError("This run is not retryable; start a new run instead")

        if run.challenge_id is not None:
            challenge = await self._challenges.get(UUID(str(run.challenge_id)))
            if challenge is not None and challenge.status in (
                ChallengeStatus.OPEN,
                ChallengeStatus.ACKNOWLEDGED,
                ChallengeStatus.HUMAN_ACTION_REQUIRED,
            ):
                raise ValidationError(
                    "A challenge on this run is still open for human resolution"
                )

        application = await self._get_owned_application(run.application_id)
        job = await self._jobs.get_for_candidate(application.job_id, self._candidate_id)
        if job is None:
            raise NotFoundError("Job not found")
        company = await self._companies.get(job.company_id)
        provider = await self._providers.get(run.provider_id) if run.provider_id else None
        if provider is None:
            provider = await self._ensure_provider(job, company)
        approved = await self._get_approved_approval(application)

        run = await self._runs.update(
            run,
            status=AutomationRunStatus.RUNNING,
            next_retry_at=None,
            last_error=None,
            context_metadata={
                **(run.context_metadata or {}),
                "retried_at": datetime.now(UTC).isoformat(),
            },
        )
        await self._audit.log(
            "automation.run_retried",
            actor_id=self._actor_id,
            candidate_id=self._candidate_id,
            entity_type="automation_run",
            entity_id=run.id,
            metadata={"application_id": str(application.id), "attempt": run.attempt_count + 1},
        )
        return await self._attempt(run, application, job, company, approved)

    # ------------------------------------------------------------------ reads

    async def list_runs(
        self,
        *,
        status: AutomationRunStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AutomationRun], int]:
        await self._ensure_owned_candidate()
        items = await self._runs.list_for_candidate(
            self._candidate_id, status=status, limit=limit, offset=offset
        )
        total = await self._runs.count_for_candidate(self._candidate_id, status=status)
        return items, total

    async def get_run(self, run_id: UUID) -> AutomationRun:
        await self._ensure_owned_candidate()
        return await self._get_owned_run(run_id)

    async def summary(self) -> dict[str, int]:
        await self._ensure_owned_candidate()
        counts = await self._runs.count_by_status(self._candidate_id)
        return {
            "total": await self._runs.count_for_candidate(self._candidate_id),
            "in_progress": counts.get(AutomationRunStatus.RUNNING, 0)
            + counts.get(AutomationRunStatus.PENDING, 0),
            "paused_human_action": counts.get(AutomationRunStatus.PAUSED_HUMAN_ACTION, 0),
            "submitted": counts.get(AutomationRunStatus.SUBMITTED, 0),
            "failed": counts.get(AutomationRunStatus.FAILED, 0),
        }

    # --------------------------------------------------------------- helpers

    def _check_application_ready(self, application: Application) -> None:
        if application.status in (ApplicationStatus.SUBMITTED, ApplicationStatus.WITHDRAWN):
            raise ValidationError(
                f"Cannot execute an application that is already {application.status.value}"
            )

    def _check_autonomy(self) -> None:
        if self._autonomy_level < 2:
            raise ValidationError(
                "Autonomy level does not permit automated application submission"
            )

    async def _get_approved_approval(self, application: Application) -> Approval:
        pending = await self._approvals.get_open_for_target(
            self._candidate_id, ApprovalKind.APPLICATION_SUBMISSION, "application", application.id
        )
        if pending is not None:
            raise ValidationError("Approval is still pending; a human decision is required first")
        approved = await self._approvals.get_approved_for_target(
            self._candidate_id, ApprovalKind.APPLICATION_SUBMISSION, "application", application.id
        )
        if approved is None:
            raise ValidationError(
                "No approved approval exists for this application; it cannot be submitted automatically"
            )
        return approved

    async def _ensure_provider(self, job: Job, company: Company | None) -> AuthProvider:
        name = f"ATS automation: {company.name if company else domain_of(job.url) or 'site'}"
        return await self._providers.get_or_create_for_site(
            name=name,
            base_url=job.url,
            provider_type=AuthProviderType.ATS if company else AuthProviderType.CAREER_SITE,
            authentication_method=AuthenticationMethod.UNKNOWN,
        )

    async def _attempt(
        self,
        run: AutomationRun,
        application: Application,
        job: Job,
        company: Company | None,
        approved: Approval,
    ) -> AutomationRun:
        documents = await self._documents.list_for_application(application.id)
        payload = SubmissionPayload(
            application_id=application.id,
            job_url=job.url,
            job_title=job.title,
            company_name=company.name if company else domain_of(job.url) or "",
            source_site=job.url,
            resume_id=application.resume_id,
            documents=[f"{d.title} (v{d.version_number})" for d in documents],
        )
        outcome = await self._submitter.submit(payload)
        return await self._handle_outcome(run, application, outcome, approved)

    async def _handle_outcome(
        self,
        run: AutomationRun,
        application: Application,
        outcome: SubmitOutcome,
        approved: Approval,
    ) -> AutomationRun:
        now = datetime.now(UTC)
        if outcome.kind == SubmitOutcomeKind.SUBMITTED:
            run = await self._runs.update(
                run,
                status=AutomationRunStatus.SUBMITTED,
                submitted_at=now,
                finished_at=now,
                last_error=None,
                result_metadata={
                    **(outcome.details or {}),
                    "message": outcome.message,
                    "approval_id": str(approved.id),
                },
            )
            application = await self._applications.update(
                application, status=ApplicationStatus.SUBMITTED
            )
            await self._audit.log(
                "automation.run_submitted",
                actor_id=self._actor_id,
                candidate_id=self._candidate_id,
                entity_type="automation_run",
                entity_id=run.id,
                metadata={
                    "application_id": str(application.id),
                    "approval_id": str(approved.id),
                    "attempt": run.attempt_count,
                },
            )
            await self._audit.log(
                "application.submitted",
                actor_id=self._actor_id,
                candidate_id=self._candidate_id,
                entity_type="application",
                entity_id=application.id,
                metadata={"automation_run_id": str(run.id)},
            )
            return run

        if outcome.kind == SubmitOutcomeKind.CHALLENGE:
            return await self._hand_off_challenge(
                run, application, outcome, approved,
                challenge_type=outcome.challenge_type or ChallengeType.UNKNOWN_HUMAN_VERIFICATION,
            )

        return await self._record_failure(run, application, outcome, approved)

    async def _hand_off_challenge(
        self,
        run: AutomationRun,
        application: Application,
        outcome: SubmitOutcome,
        approved: Approval,
        *,
        challenge_type: ChallengeType,
    ) -> AutomationRun:
        provider = await self._providers.get(run.provider_id) if run.provider_id else None
        if provider is None:
            raise ValidationError("Provider reference missing; cannot hand off the challenge")
        challenge = await self._challenges_service.ensure_open(
            provider=provider,
            challenge_type=challenge_type,
            description=outcome.message or None,
            metadata={
                "automation_run_id": str(run.id),
                "application_id": str(application.id),
            },
            human_required=True,
            severity=ChallengeSeverity.HIGH,
        )
        # ensure_open paused the linked workflow already; escalate here would
        # re-pause it (illegal transition), so mark the challenge as requiring a
        # human directly.
        challenge = await self._challenges.update(
            challenge, status=ChallengeStatus.HUMAN_ACTION_REQUIRED
        )
        run = await self._runs.update(
            run,
            status=AutomationRunStatus.PAUSED_HUMAN_ACTION,
            attempt_count=run.attempt_count + 1,
            challenge_id=str(challenge.id),
            workflow_id=str(challenge.workflow_id) if challenge.workflow_id else None,
            last_error=outcome.message or "Human verification requested by the site",
            result_metadata={
                **(run.result_metadata or {}),
                "challenge_type": challenge.challenge_type.value,
                "challenge_id": str(challenge.id),
            },
        )
        await self._audit.log(
            "automation.challenge_detected",
            actor_id=self._actor_id,
            candidate_id=self._candidate_id,
            entity_type="automation_run",
            entity_id=run.id,
            result="paused",
            metadata={
                "application_id": str(application.id),
                "challenge_id": str(challenge.id),
                "challenge_type": challenge.challenge_type.value,
            },
            details=outcome.message,
        )
        return run

    async def _record_failure(
        self,
        run: AutomationRun,
        application: Application,
        outcome: SubmitOutcome,
        approved: Approval,
    ) -> AutomationRun:
        attempts_used = run.attempt_count + 1
        exhausted = attempts_used >= run.max_attempts
        next_retry_at = None if exhausted else datetime.now(UTC) + timedelta(
            seconds=self._retry_base_seconds * (2 ** max(attempts_used - 1, 0))
        )
        run = await self._runs.update(
            run,
            status=AutomationRunStatus.FAILED,
            attempt_count=attempts_used,
            next_retry_at=next_retry_at,
            last_error=outcome.message or "Automatic submission failed",
            result_metadata={
                **(run.result_metadata or {}),
                "failure": outcome.message,
                "retryable": outcome.retryable,
            },
        )
        await self._audit.log(
            "automation.run_failed",
            actor_id=self._actor_id,
            candidate_id=self._candidate_id,
            entity_type="automation_run",
            entity_id=run.id,
            result="failed",
            metadata={
                "application_id": str(application.id),
                "attempt": attempts_used,
                "max_attempts": run.max_attempts,
                "exhausted": exhausted,
            },
            details=outcome.message,
        )
        return run
