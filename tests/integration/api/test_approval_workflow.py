"""Integration tests for the approval workflow API."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


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


async def _prepare_application(
    client: AsyncClient, candidate_id, auth_headers, job_id: str
) -> dict:
    cid = str(candidate_id)
    resp = await client.post(
        f"/api/v1/candidates/{cid}/jobs/{job_id}/match", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"/api/v1/candidates/{cid}/applications/jobs/{job_id}/prepare", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_request_approval_flow(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    job_id = await _seed_job(session, candidate.id, "ap1")
    app = await _prepare_application(client, candidate.id, auth_headers, job_id)
    cid = str(candidate.id)

    resp = await client.post(
        f"/api/v1/candidates/{cid}/applications/{app['id']}/approval-request",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    approval = resp.json()["approval"]
    assert approval["kind"] == "application_submission"
    assert approval["status"] == "pending"
    assert approval["target_id"] == app["id"]
    assert approval["context"]["match_score"] is not None

    # Idempotent re-request returns the same open approval.
    resp2 = await client.post(
        f"/api/v1/candidates/{cid}/applications/{app['id']}/approval-request",
        headers=auth_headers,
    )
    assert resp2.json()["approval"]["id"] == approval["id"]

    listing = await client.get(f"/api/v1/candidates/{cid}/approvals", headers=auth_headers)
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "pending"


async def test_approve_reject_transitions(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    job_id = await _seed_job(session, candidate.id, "ap2")
    app = await _prepare_application(client, candidate.id, auth_headers, job_id)
    cid = str(candidate.id)
    approval_id = (
        await client.post(
            f"/api/v1/candidates/{cid}/applications/{app['id']}/approval-request",
            headers=auth_headers,
        )
    ).json()["approval"]["id"]

    resp = await client.post(
        f"/api/v1/candidates/{cid}/approvals/{approval_id}/approve?note=looks+good",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"
    assert resp.json()["decision_type"] == "approve"

    # Re-approving an already-approved approval is rejected (400).
    resp = await client.post(
        f"/api/v1/candidates/{cid}/approvals/{approval_id}/reject", headers=auth_headers
    )
    assert resp.status_code == 400

    # Decisions are recorded.
    detail = await client.get(
        f"/api/v1/candidates/{cid}/approvals/{approval_id}", headers=auth_headers
    )
    assert detail.status_code == 200
    assert len(detail.json()["decisions"]) == 1
    assert detail.json()["decisions"][0]["decision_type"] == "approve"


async def test_snooze_and_cancel(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    job_id = await _seed_job(session, candidate.id, "ap3")
    app = await _prepare_application(client, candidate.id, auth_headers, job_id)
    cid = str(candidate.id)
    approval_id = (
        await client.post(
            f"/api/v1/candidates/{cid}/applications/{app['id']}/approval-request",
            headers=auth_headers,
        )
    ).json()["approval"]["id"]

    until = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    resp = await client.post(
        f"/api/v1/candidates/{cid}/approvals/{approval_id}/snooze",
        json={"until": until, "note": "later"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "snoozed"

    resp = await client.post(
        f"/api/v1/candidates/{cid}/approvals/{approval_id}/cancel", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"


async def test_cross_user_approval_hidden(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    from backend.core.security_service import get_security_service
    from backend.repositories.candidate import CandidateRepository
    from backend.repositories.user import UserRepository

    other_user = await UserRepository(session).create_user(
        "other-approval@example.com", "OtherPass123!"
    )
    other_candidate = await CandidateRepository(session).create_for_user(
        user_id=other_user.id,
        full_name="Other Candidate",
        email="other-approval@example.com",
        headline="Other",
        current_role="Other",
        total_experience_years=4,
    )
    await session.commit()
    other_headers = {
        "Authorization": (
            f"Bearer {get_security_service().create_access_token({'sub': str(other_user.id)})}"
        )
    }

    job_id = await _seed_job(session, candidate.id, "ap4")
    app = await _prepare_application(client, candidate.id, auth_headers, job_id)
    cid = str(candidate.id)
    other_cid = str(other_candidate.id)
    approval_id = (
        await client.post(
            f"/api/v1/candidates/{cid}/applications/{app['id']}/approval-request",
            headers=auth_headers,
        )
    ).json()["approval"]["id"]

    resp = await client.get(
        f"/api/v1/candidates/{cid}/approvals/{approval_id}", headers=other_headers
    )
    assert resp.status_code == 404

    resp = await client.post(
        f"/api/v1/candidates/{cid}/approvals/{approval_id}/approve", headers=other_headers
    )
    assert resp.status_code == 404

    resp = await client.post(
        f"/api/v1/candidates/{other_cid}/applications/{app['id']}/approval-request",
        headers=other_headers,
    )
    assert resp.status_code == 404
