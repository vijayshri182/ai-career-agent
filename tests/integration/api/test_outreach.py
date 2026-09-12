"""Integration tests for the outreach API (draft, approval, send, response)."""

from __future__ import annotations

from uuid import uuid4

from fastapi import Depends
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_outreach_service, get_session
from backend.app.main import app
from backend.core.config import get_settings
from backend.models.recruiter_contact import ContactSourceType, ContactType
from backend.repositories.application import ApplicationRepository
from backend.repositories.approval import ApprovalDecisionRepository, ApprovalRepository
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
from backend.repositories.recruiter_contact import (
    ContactSourceRepository,
    RecruiterContactRepository,
)
from backend.repositories.skill import SkillRepository
from backend.services.approval import ApprovalService
from backend.services.outreach import OutreachService


def _build_override(candidate, user, *, daily_limit: int = 20, approval_required: bool = True):
    def _get_service(session: AsyncSession = Depends(get_session)) -> OutreachService:
        settings = get_settings()
        audit_repo = AuditRepository(session)
        approval_repo = ApprovalRepository(session)
        approval_service = ApprovalService(
            approval_repo=approval_repo,
            decision_repo=ApprovalDecisionRepository(session),
            candidate_repo=CandidateRepository(session),
            audit_repo=audit_repo,
            actor_id=user.id,
            candidate_id=candidate.id,
            autonomy_level=settings.autonomy_level,
        )
        return OutreachService(
            candidate_repo=CandidateRepository(session),
            contact_repo=RecruiterContactRepository(session),
            job_repo=JobRepository(session),
            company_repo=CompanyRepository(session),
            skill_repo=SkillRepository(session),
            experience_repo=ExperienceRepository(session),
            education_repo=EducationRepository(session),
            certification_repo=CertificationRepository(session),
            match_repo=JobMatchRepository(session),
            application_repo=ApplicationRepository(session),
            message_repo=OutreachMessageRepository(session),
            version_repo=OutreachMessageVersionRepository(session),
            run_repo=OutreachRunRepository(session),
            audit_repo=audit_repo,
            approval_repo=approval_repo,
            approval_service=approval_service,
            actor_id=user.id,
            candidate_id=candidate.id,
            autonomy_level=settings.autonomy_level,
            approval_required=approval_required,
            daily_limit=daily_limit,
            max_attempts=settings.outreach_max_attempts,
            retry_base_seconds=settings.outreach_retry_base_seconds,
        )

    return _get_service


async def _seed_contact(
    session: AsyncSession,
    candidate_id,
    *,
    handle: str,
    email: str | None = "public.recruiter@acme.test",
    verified: bool = True,
    suppressed: bool = False,
    company_id=None,
):
    if company_id is None:
        company = await CompanyRepository(session).get_or_create_by_domain(
            name="Acme Networks", domain="acme.test"
        )
        company_id = company.id
    source = await ContactSourceRepository(session).create(
        candidate_id=candidate_id,
        company_id=company_id,
        source_type=ContactSourceType.TEAM_PAGE,
        url=f"https://careers.test/source/{handle}",
        title="Acme Team Page",
    )
    contact = await RecruiterContactRepository(session).create(
        candidate_id=candidate_id,
        company_id=company_id,
        job_id=None,
        source_id=source.id,
        full_name="Alex Rivera",
        role_title="Talent Acquisition Recruiter",
        public_profile_url=f"https://careers.test/profile/{handle}",
        email=email,
        confidence_score=95 if verified else 40,
        contact_type=ContactType.VERIFIED if verified else ContactType.GUESSED,
        is_suppressed=suppressed,
    )
    await session.commit()
    return contact


async def _draft(client: AsyncClient, cid: str, contact_id: str, headers: dict) -> dict:
    resp = await client.post(
        f"/api/v1/candidates/{cid}/outreach/drafts",
        headers=headers,
        json={"contact_id": contact_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _submit_and_approve(
    client: AsyncClient, cid: str, message_id: str, headers: dict
) -> None:
    resp = await client.post(
        f"/api/v1/candidates/{cid}/outreach/messages/{message_id}/submit",
        headers=headers,
        json={},
    )
    assert resp.status_code == 200, resp.text
    approval_id = resp.json()["approval_id"]
    assert approval_id is not None
    resp = await client.post(
        f"/api/v1/candidates/{cid}/approvals/{approval_id}/approve?note=ok",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text


async def test_full_flow_draft_approve_send_response(
    client: AsyncClient, candidate, test_user, auth_headers, session: AsyncSession
):
    contact = await _seed_contact(session, candidate.id, handle="out-full")
    cid = str(candidate.id)
    cid_msg = str(contact.id)

    draft = await _draft(client, cid, cid_msg, auth_headers)
    assert draft["status"] == "draft"
    assert draft["subject"]
    assert draft["body"]
    assert draft["fact_sources"], "fact sources must be recorded"
    assert draft["response_status"] == "no_response"

    # Sending a non-approved draft is refused.
    resp = await client.post(
        f"/api/v1/candidates/{cid}/outreach/messages/{draft['id']}/send",
        headers=auth_headers,
    )
    assert resp.status_code == 400, resp.text
    assert "cannot send" in resp.text.lower()

    await _submit_and_approve(client, cid, draft["id"], auth_headers)

    # Send now succeeds through the recording sender.
    resp = await client.post(
        f"/api/v1/candidates/{cid}/outreach/messages/{draft['id']}/send",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    run = resp.json()
    assert run["status"] == "sent"
    assert run["provider_message_id"] == "RECORDED"

    sent = await client.get(
        f"/api/v1/candidates/{cid}/outreach/messages/{draft['id']}", headers=auth_headers
    )
    assert sent.status_code == 200
    assert sent.json()["status"] == "sent"
    assert sent.json()["sent_at"] is not None

    # A second send of the same message is refused.
    resp = await client.post(
        f"/api/v1/candidates/{cid}/outreach/messages/{draft['id']}/send",
        headers=auth_headers,
    )
    assert resp.status_code == 400, resp.text

    # Follow-up can be drafted from a sent message and is reply-prefixed.
    resp = await client.post(
        f"/api/v1/candidates/{cid}/outreach/follow-ups",
        headers=auth_headers,
        json={"parent_message_id": draft["id"]},
    )
    assert resp.status_code == 201, resp.text
    fu = resp.json()
    assert fu["is_follow_up"] is True
    assert fu["subject"].startswith("Re: ")
    assert fu["parent_id"] == draft["id"]

    # Follow-up itself needs its own approval before sending.
    resp = await client.post(
        f"/api/v1/candidates/{cid}/outreach/messages/{fu['id']}/send",
        headers=auth_headers,
    )
    assert resp.status_code == 400, resp.text

    # Responding to the original sent message marks it as responded.
    resp = await client.post(
        f"/api/v1/candidates/{cid}/outreach/messages/{draft['id']}/respond",
        headers=auth_headers,
        json={"note": "Scheduled a call"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["response_status"] == "responded"

    # Summary reflects one sent message.
    status = await client.get(
        f"/api/v1/candidates/{cid}/outreach/status", headers=auth_headers
    )
    assert status.status_code == 200
    assert status.json()["sent"] == 1
    assert status.json()["responded"] == 1
    assert status.json()["sent_today"] == 1


async def test_send_blocked_while_approval_pending(
    client: AsyncClient, candidate, test_user, auth_headers, session: AsyncSession
):
    contact = await _seed_contact(session, candidate.id, handle="out-pending")
    cid = str(candidate.id)
    draft = await _draft(client, cid, str(contact.id), auth_headers)

    resp = await client.post(
        f"/api/v1/candidates/{cid}/outreach/messages/{draft['id']}/submit",
        headers=auth_headers,
        json={},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "pending_approval"
    assert resp.json()["approval_required"] is True

    resp = await client.post(
        f"/api/v1/candidates/{cid}/outreach/messages/{draft['id']}/send",
        headers=auth_headers,
    )
    assert resp.status_code == 400, resp.text
    assert "pending" in resp.text.lower()


async def test_suppressed_contact_is_blocked(
    client: AsyncClient, candidate, test_user, auth_headers, session: AsyncSession
):
    contact = await _seed_contact(session, candidate.id, handle="out-sup", suppressed=True)
    cid = str(candidate.id)
    resp = await client.post(
        f"/api/v1/candidates/{cid}/outreach/drafts",
        headers=auth_headers,
        json={"contact_id": str(contact.id)},
    )
    assert resp.status_code == 400, resp.text
    assert "suppressed" in resp.text.lower()


async def test_unverified_contact_is_blocked(
    client: AsyncClient, candidate, test_user, auth_headers, session: AsyncSession
):
    contact = await _seed_contact(session, candidate.id, handle="out-guess", verified=False)
    cid = str(candidate.id)
    resp = await client.post(
        f"/api/v1/candidates/{cid}/outreach/drafts",
        headers=auth_headers,
        json={"contact_id": str(contact.id)},
    )
    assert resp.status_code == 400, resp.text
    assert "verified" in resp.text.lower()


async def test_send_requires_verified_destination(
    client: AsyncClient, candidate, test_user, auth_headers, session: AsyncSession
):
    contact = await _seed_contact(session, candidate.id, handle="out-noemail", email=None)
    cid = str(candidate.id)
    draft = await _draft(client, cid, str(contact.id), auth_headers)
    await _submit_and_approve(client, cid, draft["id"], auth_headers)

    resp = await client.post(
        f"/api/v1/candidates/{cid}/outreach/messages/{draft['id']}/send",
        headers=auth_headers,
    )
    assert resp.status_code == 400, resp.text
    assert "email" in resp.text.lower()


async def test_daily_limit_is_enforced(
    client: AsyncClient, candidate, test_user, auth_headers, session: AsyncSession
):
    app.dependency_overrides[get_outreach_service] = _build_override(
        candidate, test_user, daily_limit=1
    )
    first = await _seed_contact(session, candidate.id, handle="out-cap-a")
    second = await _seed_contact(session, candidate.id, handle="out-cap-b")
    cid = str(candidate.id)

    draft_a = await _draft(client, cid, str(first.id), auth_headers)
    await _submit_and_approve(client, cid, draft_a["id"], auth_headers)
    resp = await client.post(
        f"/api/v1/candidates/{cid}/outreach/messages/{draft_a['id']}/send",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    draft_b = await _draft(client, cid, str(second.id), auth_headers)
    await _submit_and_approve(client, cid, draft_b["id"], auth_headers)
    resp = await client.post(
        f"/api/v1/candidates/{cid}/outreach/messages/{draft_b['id']}/send",
        headers=auth_headers,
    )
    assert resp.status_code == 400, resp.text
    assert "daily" in resp.text.lower()
    app.dependency_overrides.pop(get_outreach_service, None)


async def test_edit_only_allowed_on_drafts(
    client: AsyncClient, candidate, test_user, auth_headers, session: AsyncSession
):
    contact = await _seed_contact(session, candidate.id, handle="out-edit")
    cid = str(candidate.id)
    draft = await _draft(client, cid, str(contact.id), auth_headers)

    resp = await client.put(
        f"/api/v1/candidates/{cid}/outreach/messages/{draft['id']}",
        headers=auth_headers,
        json={"subject": "Updated subject", "body": "Updated body."},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["subject"] == "Updated subject"

    detail = await client.get(
        f"/api/v1/candidates/{cid}/outreach/messages/{draft['id']}/detail",
        headers=auth_headers,
    )
    assert detail.status_code == 200
    assert len(detail.json()["versions"]) == 2

    await _submit_and_approve(client, cid, draft["id"], auth_headers)
    resp = await client.put(
        f"/api/v1/candidates/{cid}/outreach/messages/{draft['id']}",
        headers=auth_headers,
        json={"subject": "Too late", "body": "No"},
    )
    assert resp.status_code == 400

    # Cancel is allowed, and a cancelled message cannot be sent.
    resp = await client.post(
        f"/api/v1/candidates/{cid}/outreach/messages/{draft['id']}/cancel",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    resp = await client.post(
        f"/api/v1/candidates/{cid}/outreach/messages/{draft['id']}/send",
        headers=auth_headers,
    )
    assert resp.status_code == 400


async def test_outreach_is_candidate_scoped(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    contact = await _seed_contact(session, candidate.id, handle="out-scope")
    cid = str(candidate.id)
    draft = await _draft(client, cid, str(contact.id), auth_headers)

    other = str(uuid4())
    resp = await client.post(
        f"/api/v1/candidates/{other}/outreach/drafts",
        headers=auth_headers,
        json={"contact_id": str(contact.id)},
    )
    assert resp.status_code == 404
    resp = await client.get(
        f"/api/v1/candidates/{other}/outreach/messages/{draft['id']}", headers=auth_headers
    )
    assert resp.status_code == 404
    resp = await client.get(
        f"/api/v1/candidates/{other}/outreach/status", headers=auth_headers
    )
    assert resp.status_code == 404
    resp = await client.get(
        f"/api/v1/candidates/{other}/outreach/runs/{uuid4()}", headers=auth_headers
    )
    assert resp.status_code == 404
