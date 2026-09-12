"""Integration tests for the permitted application automation API."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Depends
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_application_automation_service, get_session
from backend.app.main import app
from backend.core.config import get_settings
from backend.models.challenge import ChallengeType
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
from backend.services.application_automation import ApplicationAutomationService
from backend.services.authentication_provider import AuthProviderService
from backend.services.automation_adapter import (
    SubmitOutcome,
    SubmitOutcomeKind,
)
from backend.services.challenge import ChallengeService
from backend.services.human_in_loop import HumanInTheLoopService


class _ApiChallengeSubmitter:
    def __init__(self, challenge_type: ChallengeType = ChallengeType.CAPTCHA) -> None:
        self._challenge_type = challenge_type

    async def submit(self, payload):
        return SubmitOutcome(
            kind=SubmitOutcomeKind.CHALLENGE,
            message="CAPTCHA required",
            retryable=True,
            challenge_type=self._challenge_type,
        )


def _build_automation_override(candidate, user, *, submitter=None):
    def _get_service(session: AsyncSession = Depends(get_session)) -> ApplicationAutomationService:
        settings = get_settings()
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
            ChallengeRepository(session),
            audit_repo,
            provider_service,
            workflow_service,
            user.id,
            candidate.id,
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
            autonomy_level=settings.autonomy_level,
            automation_enabled=settings.automation_enabled,
            max_attempts=settings.automation_max_attempts,
            retry_base_seconds=settings.automation_retry_base_seconds,
            submitter=submitter,
        )

    return _get_service


async def _seed_job(session: AsyncSession, candidate_id, cid: str) -> str:
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
    job = await JobRepository(session).create(
        candidate_id=candidate_id,
        company_id=company.id,
        source_id=source.id,
        url=f"https://careers.test/jobs/{cid}",
        title="Senior Software Engineer",
        location="Bangalore, India",
        description=(
            "Qualifications:\n- 5+ years of software engineering\n- Python\n- Kubernetes\n"
        ),
        content_hash=f"hash-{cid}",
        first_seen_at=now,
        last_seen_at=now,
    )
    return str(job.id)


async def _prepare_and_approve(
    client: AsyncClient, candidate_id, auth_headers, job_id: str
) -> str:
    cid = str(candidate_id)
    resp = await client.post(
        f"/api/v1/candidates/{cid}/jobs/{job_id}/match", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"/api/v1/candidates/{cid}/applications/jobs/{job_id}/prepare", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    app_id = resp.json()["id"]

    approval = (
        await client.post(
            f"/api/v1/candidates/{cid}/applications/{app_id}/approval-request",
            headers=auth_headers,
        )
    ).json()["approval"]
    resp = await client.post(
        f"/api/v1/candidates/{cid}/approvals/{approval['id']}/approve?note=ok",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    return app_id


async def test_execute_requires_approval_then_submits(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    job_id = await _seed_job(session, candidate.id, "au1")
    cid = str(candidate.id)
    await client.post(f"/api/v1/candidates/{cid}/jobs/{job_id}/match", headers=auth_headers)
    app_id = (
        await client.post(
            f"/api/v1/candidates/{cid}/applications/jobs/{job_id}/prepare",
            headers=auth_headers,
        )
    ).json()["id"]

    # No approval -> execution is refused.
    resp = await client.post(
        f"/api/v1/candidates/{cid}/applications/{app_id}/execute", headers=auth_headers
    )
    assert resp.status_code == 400, resp.text
    assert "approval" in resp.text

    # Approved flow submits.
    approval = (
        await client.post(
            f"/api/v1/candidates/{cid}/applications/{app_id}/approval-request",
            headers=auth_headers,
        )
    ).json()["approval"]
    resp = await client.post(
        f"/api/v1/candidates/{cid}/approvals/{approval['id']}/approve?note=ok",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    resp = await client.post(
        f"/api/v1/candidates/{cid}/applications/{app_id}/execute", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "submitted"
    assert body["application_id"] == app_id
    assert body["attempt_count"] == 0

    # Status summary reflects the submission.
    status = await client.get(f"/api/v1/candidates/{cid}/automation/status", headers=auth_headers)
    assert status.status_code == 200
    assert status.json()["submitted"] == 1

    # Runs list + detail are accessible.
    runs = await client.get(
        f"/api/v1/candidates/{cid}/automation/runs?status=submitted", headers=auth_headers
    )
    assert runs.status_code == 200
    assert runs.json()["total"] == 1

    run_detail = await client.get(
        f"/api/v1/candidates/{cid}/automation/runs/{body['id']}", headers=auth_headers
    )
    assert run_detail.status_code == 200
    assert run_detail.json()["status"] == "submitted"

    # Submitting again is rejected.
    resp = await client.post(
        f"/api/v1/candidates/{cid}/applications/{app_id}/execute", headers=auth_headers
    )
    assert resp.status_code == 400

    # Retrying an already-submitted run is rejected.
    resp = await client.post(
        f"/api/v1/candidates/{cid}/automation/runs/{body['id']}/retry", headers=auth_headers
    )
    assert resp.status_code == 400


async def test_execute_challenge_handoff_pauses_run(
    client: AsyncClient, candidate, test_user, auth_headers, session: AsyncSession
):
    app.dependency_overrides[get_application_automation_service] = (
        _build_automation_override(candidate, test_user, submitter=_ApiChallengeSubmitter())
    )
    job_id = await _seed_job(session, candidate.id, "au2")
    cid = str(candidate.id)
    app_id = await _prepare_and_approve(client, candidate.id, auth_headers, job_id)

    resp = await client.post(
        f"/api/v1/candidates/{cid}/applications/{app_id}/execute", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "paused_human_action"
    assert body["challenge_id"] is not None

    status = await client.get(f"/api/v1/candidates/{cid}/automation/status", headers=auth_headers)
    assert status.status_code == 200
    assert status.json()["paused_human_action"] == 1

    # Retry while the challenge is still open is blocked (400).
    resp = await client.post(
        f"/api/v1/candidates/{cid}/automation/runs/{body['id']}/retry", headers=auth_headers
    )
    assert resp.status_code == 400
    assert "human resolution" in resp.text
    app.dependency_overrides.pop(get_application_automation_service, None)


async def test_automation_is_candidate_scoped(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    job_id = await _seed_job(session, candidate.id, "au3")
    cid = str(candidate.id)
    app_id = await _prepare_and_approve(client, candidate.id, auth_headers, job_id)
    run_id = (
        await client.post(
            f"/api/v1/candidates/{cid}/applications/{app_id}/execute", headers=auth_headers
        )
    ).json()["id"]

    # A random unknown candidate id yields 404 from the ownership gate, not data.
    resp = await client.get(
        f"/api/v1/candidates/{uuid4()}/automation/runs/{run_id}", headers=auth_headers
    )
    assert resp.status_code == 404
