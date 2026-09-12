"""Unit tests for the permitted application automation service."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import NotFoundError, ValidationError
from backend.models.application import Application, ApplicationStatus
from backend.models.automation_run import AutomationRunStatus
from backend.models.challenge import ChallengeStatus, ChallengeType
from backend.services.application_automation import ApplicationAutomationService
from backend.services.automation_adapter import (
    SubmitOutcome,
    SubmitOutcomeKind,
)


class _ChallengeSubmitter:
    def __init__(self, challenge_type: ChallengeType = ChallengeType.CAPTCHA) -> None:
        self._challenge_type = challenge_type

    async def submit(self, payload):
        return SubmitOutcome(
            kind=SubmitOutcomeKind.CHALLENGE,
            message="CAPTCHA required",
            retryable=True,
            challenge_type=self._challenge_type,
        )


class _FailingSubmitter:
    def __init__(self, retryable: bool = True) -> None:
        self._retryable = retryable

    async def submit(self, payload):
        return SubmitOutcome(
            kind=SubmitOutcomeKind.FAILED,
            message="ATS returned 500",
            retryable=self._retryable,
        )


class _ChallengeThenSuccessSubmitter:
    def __init__(self, challenge_type: ChallengeType = ChallengeType.CAPTCHA) -> None:
        self._challenge_type = challenge_type
        self._calls = 0

    async def submit(self, payload):
        self._calls += 1
        if self._calls == 1:
            return SubmitOutcome(
                kind=SubmitOutcomeKind.CHALLENGE,
                message="CAPTCHA required",
                retryable=True,
                challenge_type=self._challenge_type,
            )
        return SubmitOutcome(
            kind=SubmitOutcomeKind.SUBMITTED,
            message="Submission recorded",
        )


def _build_service(
    session: AsyncSession,
    candidate,
    user,
    *,
    autonomy_level: int = 2,
    max_attempts: int = 3,
    submitter=None,
) -> ApplicationAutomationService:
    from backend.repositories.application import (
        ApplicationDocumentRepository,
        ApplicationRepository,
    )
    from backend.repositories.approval import ApprovalRepository
    from backend.repositories.audit import AuditRepository
    from backend.repositories.authentication_provider import (
        AuthProviderRepository,
        AuthStateRepository,
    )
    from backend.repositories.automation_run import AutomationRunRepository
    from backend.repositories.candidate import CandidateRepository
    from backend.repositories.challenge import ChallengeRepository
    from backend.repositories.company import CompanyRepository
    from backend.repositories.job import JobRepository
    from backend.repositories.job_source import JobSourceRepository
    from backend.repositories.workflow_run import WorkflowRunRepository
    from backend.services.authentication_provider import AuthProviderService
    from backend.services.challenge import ChallengeService
    from backend.services.human_in_loop import HumanInTheLoopService

    audit_repo = AuditRepository(session)
    candidate_repo = CandidateRepository(session)
    provider_service = AuthProviderService(
        AuthProviderRepository(session),
        AuthStateRepository(session),
        candidate_repo,
        audit_repo,
        user.id,
        candidate.id,
    )
    workflow_service = HumanInTheLoopService(
        WorkflowRunRepository(session), audit_repo, user.id, candidate.id
    )
    challenge_service = ChallengeService(
        ChallengeRepository(session), audit_repo, provider_service, workflow_service, user.id, candidate.id
    )
    return ApplicationAutomationService(
        candidate_repo=candidate_repo,
        job_repo=JobRepository(session),
        company_repo=CompanyRepository(session),
        job_source_repo=JobSourceRepository(session),
        application_repo=ApplicationRepository(session),
        document_repo=ApplicationDocumentRepository(session),
        run_repo=AutomationRunRepository(session),
        approval_repo=ApprovalRepository(session),
        audit_repo=audit_repo,
        challenge_repo=ChallengeRepository(session),
        provider_service=provider_service,
        challenge_service=challenge_service,
        actor_id=user.id,
        candidate_id=candidate.id,
        autonomy_level=autonomy_level,
        automation_enabled=True,
        max_attempts=max_attempts,
        retry_base_seconds=60,
        submitter=submitter,
    )


async def _seed_submittable(session: AsyncSession, candidate, cid: str, *, allow_automation: bool = True) -> Application:
    from backend.repositories.application import ApplicationRepository
    from backend.repositories.company import CompanyRepository
    from backend.repositories.job import JobRepository
    from backend.repositories.job_source import JobSourceRepository

    company = await CompanyRepository(session).get_or_create_by_domain(
        name="Acme Networks", domain="acme.test"
    )
    source_repo = JobSourceRepository(session)
    sources = await source_repo.list_for_candidate(candidate.id)
    source = next((s for s in sources if s.name == "Careers API"), None)
    if source is None:
        source = await source_repo.create(
            candidate_id=candidate.id,
            name="Careers API",
            source_type="api",
            base_url="https://careers.test",
            terms_allow_automation=allow_automation,
            is_enabled=True,
        )
    else:
        source = await source_repo.update(source, terms_allow_automation=allow_automation, is_enabled=True)
    job = await JobRepository(session).create(
        candidate_id=candidate.id,
        company_id=company.id,
        source_id=source.id,
        url=f"https://careers.test/jobs/{cid}",
        title="Senior Software Engineer",
        location="Bangalore, India",
        description="Qualifications:\n- 5+ years of software engineering\n- Python\n- Kubernetes\n",
        content_hash=f"hash-{cid}",
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    return await ApplicationRepository(session).create(
        candidate_id=candidate.id,
        job_id=job.id,
        status=ApplicationStatus.READY,
    )


async def _approve_for_application(session: AsyncSession, candidate, user, application: Application):
    from backend.models.approval import ApprovalDecisionType, ApprovalKind
    from backend.repositories.approval import ApprovalDecisionRepository, ApprovalRepository
    from backend.repositories.audit import AuditRepository
    from backend.repositories.candidate import CandidateRepository
    from backend.services.approval import ApprovalService

    service = ApprovalService(
        approval_repo=ApprovalRepository(session),
        decision_repo=ApprovalDecisionRepository(session),
        candidate_repo=CandidateRepository(session),
        audit_repo=AuditRepository(session),
        actor_id=user.id,
        candidate_id=candidate.id,
        autonomy_level=2,
    )
    approval = await service.request_approval(
        kind=ApprovalKind.APPLICATION_SUBMISSION,
        target_type="application",
        target_id=application.id,
        summary="Submit prepared application",
        context={"match_score": 82.0},
    )
    await service.decide(approval.id, ApprovalDecisionType.APPROVE, note="Approved")


async def test_execute_requires_approved_approval(session, candidate, test_user):
    app = await _seed_submittable(session, candidate, "u1")
    service = _build_service(session, candidate, test_user)
    with pytest.raises(ValidationError, match="No approved approval"):
        await service.execute(app.id)
    await session.commit()


async def test_execute_blocked_while_approval_still_pending(session, candidate, test_user):
    from backend.models.approval import ApprovalKind
    from backend.repositories.approval import ApprovalDecisionRepository, ApprovalRepository
    from backend.repositories.audit import AuditRepository
    from backend.repositories.candidate import CandidateRepository
    from backend.services.approval import ApprovalService

    app = await _seed_submittable(session, candidate, "u2")
    approval_service = ApprovalService(
        approval_repo=ApprovalRepository(session),
        decision_repo=ApprovalDecisionRepository(session),
        candidate_repo=CandidateRepository(session),
        audit_repo=AuditRepository(session),
        actor_id=test_user.id,
        candidate_id=candidate.id,
        autonomy_level=2,
    )
    await approval_service.request_approval(
        kind=ApprovalKind.APPLICATION_SUBMISSION,
        target_type="application",
        target_id=app.id,
        summary="Pending",
    )
    service = _build_service(session, candidate, test_user)
    with pytest.raises(ValidationError, match="still pending"):
        await service.execute(app.id)
    await session.commit()


async def test_execute_requires_source_permission(session, candidate, test_user):
    app = await _seed_submittable(session, candidate, "u3", allow_automation=False)
    await _approve_for_application(session, candidate, test_user, app)
    service = _build_service(session, candidate, test_user)
    with pytest.raises(ValidationError, match="does not explicitly permit"):
        await service.execute(app.id)
    await session.commit()


async def test_execute_requires_autonomy_level_2(session, candidate, test_user):
    app = await _seed_submittable(session, candidate, "u4")
    await _approve_for_application(session, candidate, test_user, app)
    service = _build_service(session, candidate, test_user, autonomy_level=1)
    with pytest.raises(ValidationError, match="Autonomy level"):
        await service.execute(app.id)
    await session.commit()


async def test_execute_submits_application_and_run(session, candidate, test_user):
    app = await _seed_submittable(session, candidate, "u5")
    await _approve_for_application(session, candidate, test_user, app)
    service = _build_service(session, candidate, test_user)
    run = await service.execute(app.id)
    await session.commit()
    assert run.status == AutomationRunStatus.SUBMITTED
    assert run.attempt_count == 0
    assert run.provider_id is not None
    stored_app = await service._applications.get(app.id)
    assert stored_app is not None and stored_app.status == ApplicationStatus.SUBMITTED
    summary = await service.summary()
    assert summary["submitted"] == 1


async def test_cannot_execute_already_submitted_application(session, candidate, test_user):
    app = await _seed_submittable(session, candidate, "u6")
    await _approve_for_application(session, candidate, test_user, app)
    service = _build_service(session, candidate, test_user)
    await service.execute(app.id)
    with pytest.raises(ValidationError, match="already submitted"):
        await service.execute(app.id)
    await session.commit()


async def test_challenge_handoff_pauses_run(session, candidate, test_user):
    app = await _seed_submittable(session, candidate, "u7")
    await _approve_for_application(session, candidate, test_user, app)
    service = _build_service(
        session, candidate, test_user, submitter=_ChallengeSubmitter(ChallengeType.CAPTCHA)
    )
    run = await service.execute(app.id)
    await session.commit()
    assert run.status == AutomationRunStatus.PAUSED_HUMAN_ACTION
    assert run.challenge_id is not None
    stored_app = await service._applications.get(app.id)
    assert stored_app is not None and stored_app.status != ApplicationStatus.SUBMITTED


async def test_challenge_in_flight_blocks_retry(session, candidate, test_user):
    app = await _seed_submittable(session, candidate, "u8")
    await _approve_for_application(session, candidate, test_user, app)
    service = _build_service(
        session, candidate, test_user, submitter=_ChallengeSubmitter(ChallengeType.CAPTCHA)
    )
    run = await service.execute(app.id)
    await session.commit()
    with pytest.raises(ValidationError, match="still open for human resolution"):
        await service.retry(run.id)
    await session.commit()


async def test_retry_after_challenge_resolved_submits(session, candidate, test_user):
    from uuid import UUID

    from backend.models.challenge import ChallengeResolution

    app = await _seed_submittable(session, candidate, "u9")
    await _approve_for_application(session, candidate, test_user, app)
    service = _build_service(
        session, candidate, test_user, submitter=_ChallengeThenSuccessSubmitter()
    )
    run = await service.execute(app.id)
    await session.commit()
    assert run.status == AutomationRunStatus.PAUSED_HUMAN_ACTION
    assert run.challenge_id is not None

    challenge = await service._challenges.get(UUID(run.challenge_id))
    assert challenge is not None
    challenge = await service._challenges.update(
        challenge,
        status=ChallengeStatus.RESOLVED,
        resolved_at=datetime.now(UTC),
        resolution_method=ChallengeResolution.HUMAN,
    )
    await session.commit()

    retried = await service.retry(run.id)
    await session.commit()
    assert retried.status == AutomationRunStatus.SUBMITTED
    assert retried.attempt_count == 1
    stored_app = await service._applications.get(app.id)
    assert stored_app is not None and stored_app.status == ApplicationStatus.SUBMITTED


async def test_failed_retryable_run_schedules_backoff(session, candidate, test_user):
    app = await _seed_submittable(session, candidate, "u10")
    await _approve_for_application(session, candidate, test_user, app)
    service = _build_service(session, candidate, test_user, submitter=_FailingSubmitter())
    run = await service.execute(app.id)
    await session.commit()
    assert run.status == AutomationRunStatus.FAILED
    assert run.attempt_count == 1
    assert run.next_retry_at is not None


async def test_attempt_budget_exhaustion_blocks_retry(session, candidate, test_user):
    app = await _seed_submittable(session, candidate, "u11")
    await _approve_for_application(session, candidate, test_user, app)
    service = _build_service(
        session, candidate, test_user, max_attempts=2, submitter=_FailingSubmitter()
    )
    run = await service.execute(app.id)
    await session.commit()
    assert run.next_retry_at is not None
    retried = await service.retry(run.id)
    assert retried.attempt_count == 2
    assert retried.next_retry_at is None
    with pytest.raises(ValidationError, match="Maximum retry attempts"):
        await service.retry(retried.id)
    await session.commit()


async def test_failed_retry_pending_blocks_new_execute(session, candidate, test_user):
    app = await _seed_submittable(session, candidate, "u12")
    await _approve_for_application(session, candidate, test_user, app)
    service = _build_service(session, candidate, test_user, submitter=_FailingSubmitter())
    await service.execute(app.id)
    await session.commit()
    with pytest.raises(ValidationError, match="retry-pending"):
        await service.execute(app.id)
    await session.commit()


async def test_get_run_hides_other_candidate(session, candidate, test_user):
    app = await _seed_submittable(session, candidate, "u13")
    await _approve_for_application(session, candidate, test_user, app)
    service = _build_service(session, candidate, test_user)
    run = await service.execute(app.id)
    other = _build_service(session, candidate, test_user)
    other._candidate_id = uuid4()
    with pytest.raises(NotFoundError):
        await other.get_run(run.id)
    await session.commit()


async def test_list_runs_and_summary(session, candidate, test_user):
    app = await _seed_submittable(session, candidate, "u14")
    await _approve_for_application(session, candidate, test_user, app)
    service = _build_service(session, candidate, test_user)
    await service.execute(app.id)
    items, total = await service.list_runs()
    assert total == 1
    assert items[0].status == AutomationRunStatus.SUBMITTED
    filtered, filtered_total = await service.list_runs(status=AutomationRunStatus.SUBMITTED)
    assert filtered_total == 1
    none, none_total = await service.list_runs(status=AutomationRunStatus.FAILED)
    assert none_total == 0
    await session.commit()
