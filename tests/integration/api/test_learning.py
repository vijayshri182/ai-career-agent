"""Integration tests for the learning / optimization API (Phase 12)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security_service import get_security_service
from backend.models.application import ApplicationStatus
from backend.models.candidate import CandidateSkill, Certification, Education, Experience
from backend.models.job_match import JobMatchStatus
from backend.models.outreach import OutreachStatus
from backend.models.recruiter_contact import ContactSourceType, ContactType
from backend.repositories.application import ApplicationRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.company import CompanyRepository
from backend.repositories.job import JobRepository
from backend.repositories.job_match import JobMatchRepository
from backend.repositories.job_source import JobSourceRepository
from backend.repositories.outreach import OutreachMessageRepository
from backend.repositories.recruiter_contact import (
    ContactSourceRepository,
    RecruiterContactRepository,
)
from backend.repositories.skill import SkillRepository
from backend.repositories.user import UserRepository


async def _seed_profile(
    session: AsyncSession,
    candidate_id,
    *,
    skills: tuple[str, ...] = ("Python", "FastAPI", "PostgreSQL"),
    experience: bool = True,
    education: bool = True,
    certification: bool = True,
) -> None:
    for name in skills:
        session.add(CandidateSkill(candidate_id=candidate_id, name=name, is_primary=True))
    if experience:
        session.add(
            Experience(
                candidate_id=candidate_id,
                company_name="Telco Systems",
                title="Engineering Lead",
                start_date=date(2018, 1, 1),
                is_current=True,
                technologies=["Python"],
            )
        )
    if education:
        session.add(
            Education(
                candidate_id=candidate_id,
                institution="National Institute of Technology",
                degree="B.Tech",
                field_of_study="Computer Science",
            )
        )
    if certification:
        session.add(
            Certification(
                candidate_id=candidate_id,
                name="AWS Solutions Architect",
                issuing_organization="Amazon",
            )
        )
    await session.commit()


async def _seed_job_and_match(
    session: AsyncSession,
    candidate_id,
    cid: str,
    *,
    missing_skills: tuple[str, ...] = (),
) -> dict:
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
        description="Python and Kubernetes experience required.",
        content_hash=f"hash-{cid}",
        first_seen_at=now,
        last_seen_at=now,
    )
    await session.commit()
    match = await JobMatchRepository(session).upsert(
        candidate_id,
        job.id,
        status=JobMatchStatus.MATCHED,
        score=0.9,
        confidence=0.88,
        is_match=True,
        matched_skills=["Python"],
        missing_skills=list(missing_skills),
        transferable_skills=[],
        strengths=["Python"],
        gaps=list(missing_skills),
        blockers=[],
        recommendation_reasons=[],
        rejection_reasons=[],
        score_breakdown={},
        rules_version="test",
        evaluated_at=now,
    )
    await session.commit()
    return {"job_id": job.id, "match_id": match.id}


async def _seed_submitted_application(
    session: AsyncSession, candidate_id, job_and_match: dict
) -> str:
    application = await ApplicationRepository(session).create(
        candidate_id=candidate_id,
        job_id=job_and_match["job_id"],
        status=ApplicationStatus.SUBMITTED,
        match_id=job_and_match["match_id"],
        match_score=0.9,
    )
    await session.commit()
    return str(application.id)


async def _seed_sent_message(
    session: AsyncSession, candidate_id, *, handle: str
) -> str:
    company = await CompanyRepository(session).get_or_create_by_domain(
        name="Acme Networks", domain="acme.test"
    )
    source = await ContactSourceRepository(session).create(
        candidate_id=candidate_id,
        company_id=company.id,
        source_type=ContactSourceType.TEAM_PAGE,
        url=f"https://careers.test/source/{handle}",
        title="Acme Team Page",
    )
    contact = await RecruiterContactRepository(session).create(
        candidate_id=candidate_id,
        company_id=company.id,
        job_id=None,
        source_id=source.id,
        full_name="Alex Rivera",
        role_title="Talent Acquisition Recruiter",
        public_profile_url=f"https://careers.test/profile/{handle}",
        email="public.recruiter@acme.test",
        confidence_score=95,
        contact_type=ContactType.VERIFIED,
        is_suppressed=False,
    )
    await session.commit()
    message = await OutreachMessageRepository(session).create(
        candidate_id=candidate_id,
        contact_id=contact.id,
        job_id=None,
        subject="Opportunity at Acme Networks",
        body="Hi Alex, I would like to learn more about opportunities.",
        status=OutreachStatus.SENT,
    )
    await session.commit()
    return str(message.id)


async def _make_other_candidate(session: AsyncSession) -> tuple[object, dict]:
    other_user = await UserRepository(session).create_user(
        f"other-learning-{uuid4().hex[:8]}@example.com", "StrongP@ssw0rd!"
    )
    other_candidate = await CandidateRepository(session).create_for_user(
        user_id=other_user.id,
        full_name="Other Candidate",
        email=f"other-learning-{uuid4().hex[:8]}@example.com",
        headline="Other",
        current_role="Other",
        total_experience_years=4,
    )
    await session.commit()
    headers = {
        "Authorization": f"Bearer {get_security_service().create_access_token({'sub': str(other_user.id)})}"
    }
    return other_candidate, headers


# ---------------------------------------------------------------- feedback


async def test_feedback_records_and_lists(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    seeded = await _seed_job_and_match(session, candidate.id, "fb1")
    app_id = await _seed_submitted_application(session, candidate.id, seeded)
    cid = str(candidate.id)

    resp = await client.post(
        f"/api/v1/candidates/{cid}/feedback",
        headers=auth_headers,
        json={
            "outcome": "offer_received",
            "application_id": app_id,
            "stage": "onsite_interview",
            "note": "Advanced to final round.",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["outcome"] == "offer_received"
    assert body["application_id"] == app_id
    assert body["candidate_id"] == str(candidate.id)

    listing = await client.get(
        f"/api/v1/candidates/{cid}/feedback", headers=auth_headers
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    filtered = await client.get(
        f"/api/v1/candidates/{cid}/feedback",
        headers=auth_headers,
        params={"outcome": "offer_received"},
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1

    none = await client.get(
        f"/api/v1/candidates/{cid}/feedback",
        headers=auth_headers,
        params={"outcome": "rejected"},
    )
    assert none.status_code == 200
    assert none.json()["total"] == 0


async def test_feedback_rejects_foreign_application(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    other_candidate, other_headers = await _make_other_candidate(session)
    seeded = await _seed_job_and_match(session, other_candidate.id, "fb2")
    other_app_id = await _seed_submitted_application(
        session, other_candidate.id, seeded
    )

    resp = await client.post(
        f"/api/v1/candidates/{str(candidate.id)}/feedback",
        headers=auth_headers,
        json={"outcome": "ghosted", "application_id": other_app_id},
    )
    assert resp.status_code == 404
    assert "Application not found" in resp.json()["detail"]


async def test_analytics_summary_counts(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    seeded = await _seed_job_and_match(
        session, candidate.id, "sum1", missing_skills=("Kafka", "Terraform")
    )
    await _seed_profile(session, candidate.id)
    await _seed_submitted_application(session, candidate.id, seeded)
    await _seed_sent_message(session, candidate.id, handle="sum1")
    cid = str(candidate.id)

    resp = await client.post(
        f"/api/v1/candidates/{cid}/feedback",
        headers=auth_headers,
        json={"outcome": "offer_received", "stage": "final_round"},
    )
    assert resp.status_code == 201, resp.text

    resp = await client.get(
        f"/api/v1/candidates/{cid}/analytics/summary", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["applications"]["submitted"] == 1
    assert body["applications"]["total"] == 1

    assert body["matches"]["total"] == 1
    assert body["matches"]["matched"] == 1
    assert body["matches"]["top_missing_skills"] == ["kafka", "terraform"]

    assert body["outreach"]["sent"] == 1
    assert body["outreach"]["responded"] == 0
    assert body["outreach"]["response_rate"] == 0.0

    assert body["feedback"]["total"] == 1
    assert body["feedback"]["by_outcome"] == {"offer_received": 1}

    assert body["profile"]["skills_count"] == 3
    assert body["profile"]["experiences_count"] == 1
    assert body["profile"]["educations_count"] == 1
    assert body["profile"]["certifications_count"] == 1
    assert body["profile"]["jobs_count"] == 1


# ------------------------------------------------------------ recommendations


def _title_map(items: list[dict]) -> dict[str, str]:
    return {item["source_key"]: item["title"] for item in items}


async def test_recommendations_deterministic_deduped_and_never_edit(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    await _seed_profile(session, candidate.id)
    await _seed_job_and_match(
        session, candidate.id, "r1", missing_skills=("Kafka", "Terraform")
    )
    cid = str(candidate.id)

    first = await client.post(
        f"/api/v1/candidates/{cid}/recommendations/generate", headers=auth_headers
    )
    assert first.status_code == 200, first.text
    first_items = first.json()["items"]
    first_titles = _title_map(first_items)
    assert set(first_titles) == {"skill:kafka", "skill:terraform"}
    first_ids = {item["id"] for item in first_items}
    for item in first_items:
        assert item["status"] == "active"
        assert item["rationale"]
        for field in ("title", "detail"):
            text = item[field].casefold()
            assert "gender" not in text and "race" not in text

    second = await client.post(
        f"/api/v1/candidates/{cid}/recommendations/generate", headers=auth_headers
    )
    assert second.status_code == 200
    second_items = second.json()["items"]
    assert _title_map(second_items) == first_titles
    assert {item["id"] for item in second_items} == first_ids

    listing = await client.get(
        f"/api/v1/candidates/{cid}/recommendations",
        headers=auth_headers,
        params={"status": "active"},
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 2

    assert len(await SkillRepository(session).list_for_candidate(candidate.id)) == 3
    assert (
        await JobMatchRepository(session).count_for_candidate(candidate.id, is_match=True)
        == 1
    )
    assert (
        await ApplicationRepository(session).count_for_candidate(candidate.id) == 0
    )


async def test_refresh_archives_stale_recommendations(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    await _seed_profile(session, candidate.id)
    seeded = await _seed_job_and_match(
        session, candidate.id, "r2", missing_skills=("Kafka",)
    )
    cid = str(candidate.id)

    first = await client.post(
        f"/api/v1/candidates/{cid}/recommendations/generate", headers=auth_headers
    )
    assert first.status_code == 200
    assert {item["source_key"] for item in first.json()["items"]} == {"skill:kafka"}

    await JobMatchRepository(session).upsert(
        candidate.id,
        seeded["job_id"],
        missing_skills=[],
    )
    await session.commit()

    refreshed = await client.post(
        f"/api/v1/candidates/{cid}/recommendations/generate?refresh=true",
        headers=auth_headers,
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["total"] == 0

    archived = await client.get(
        f"/api/v1/candidates/{cid}/recommendations",
        headers=auth_headers,
        params={"status": "archived"},
    )
    assert archived.status_code == 200
    assert set(_title_map(archived.json()["items"])) == {"skill:kafka"}


async def test_apply_and_outreach_recommendations_trigger(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    await _seed_profile(session, candidate.id)
    seeded = await _seed_job_and_match(
        session, candidate.id, "r3", missing_skills=("Docker",)
    )
    await _seed_submitted_application(session, candidate.id, seeded)
    await _seed_sent_message(session, candidate.id, handle="r3")
    cid = str(candidate.id)

    resp = await client.post(
        f"/api/v1/candidates/{cid}/recommendations/generate", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    keys = set(_title_map(resp.json()["items"]))
    assert "skill:docker" in keys
    assert "feedback:no_outcomes" in keys
    assert "outreach:no_responses" in keys
    kinds = {item["kind"] for item in resp.json()["items"]}
    assert {"skill_gap", "apply_optimization", "outreach_optimization"} <= kinds


async def test_recommendation_lifecycle_ack_archive(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    await _seed_profile(session, candidate.id)
    await _seed_job_and_match(
        session, candidate.id, "r4", missing_skills=("Kafka",)
    )
    cid = str(candidate.id)

    resp = await client.post(
        f"/api/v1/candidates/{cid}/recommendations/generate", headers=auth_headers
    )
    rec = resp.json()["items"][0]
    rec_id = rec["id"]

    ack = await client.post(
        f"/api/v1/candidates/{cid}/recommendations/{rec_id}/acknowledge",
        headers=auth_headers,
    )
    assert ack.status_code == 200, ack.text
    assert ack.json()["status"] == "acknowledged"

    arch = await client.post(
        f"/api/v1/candidates/{cid}/recommendations/{rec_id}/archive",
        headers=auth_headers,
    )
    assert arch.status_code == 200
    assert arch.json()["status"] == "archived"

    again = await client.post(
        f"/api/v1/candidates/{cid}/recommendations/{rec_id}/archive",
        headers=auth_headers,
    )
    assert again.status_code == 200
    assert again.json()["status"] == "archived"

    late_ack = await client.post(
        f"/api/v1/candidates/{cid}/recommendations/{rec_id}/acknowledge",
        headers=auth_headers,
    )
    assert late_ack.status_code == 400
    assert "archived" in late_ack.json()["detail"]


async def test_recommendations_are_candidate_scoped(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    await _seed_profile(session, candidate.id)
    await _seed_job_and_match(
        session, candidate.id, "r5", missing_skills=("Kafka",)
    )
    cid = str(candidate.id)
    other_candidate, other_headers = await _make_other_candidate(session)

    resp = await client.post(
        f"/api/v1/candidates/{cid}/recommendations/generate", headers=auth_headers
    )
    rec_id = resp.json()["items"][0]["id"]

    blocked = await client.post(
        f"/api/v1/candidates/{cid}/recommendations/{rec_id}/acknowledge",
        headers=other_headers,
    )
    assert blocked.status_code == 404

    foreign = await client.get(
        f"/api/v1/candidates/{str(other_candidate.id)}/recommendations",
        headers=other_headers,
    )
    assert foreign.status_code == 200
    assert foreign.json()["total"] == 0
