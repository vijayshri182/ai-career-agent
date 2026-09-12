"""Integration tests for the application preparation API (fact-grounded materials)."""

from datetime import UTC, date, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _seed_job(session: AsyncSession, candidate_id, cid: str) -> dict:
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
            "Qualifications:\n"
            "- 5+ years of software engineering experience\n"
            "- Must have Python\n"
            "- Must have Kubernetes\n"
            "- Must have Kafka\n"
            "Preferred: AWS."
        ),
        content_hash=f"hash-{cid}",
        first_seen_at=now,
        last_seen_at=now,
    )
    return {"id": str(job.id)}


async def _add_profile_context(session: AsyncSession, candidate) -> None:
    from backend.models.candidate import CandidateSkill, Experience
    from backend.repositories.candidate import CandidateRepository

    repo = CandidateRepository(session)
    await repo.update(
        candidate,
        target_role="Senior Software Engineer",
        work_mode_preference="remote",
        seniority="Senior",
        expected_compensation_amount=50,
        expected_compensation_currency="USD",
        career_preferences={"target_industries": ["telecommunications", "saas_software"]},
    )
    for name in ("Python", "Kubernetes", "Kafka", "AWS", "PostgreSQL", "FastAPI"):
        session.add(CandidateSkill(candidate_id=candidate.id, name=name, is_primary=True))
    session.add(
        Experience(
            candidate_id=candidate.id,
            company_name="Telco Systems",
            title="Engineering Lead",
            start_date=date(2018, 1, 1),
            is_current=True,
            domain="Telecom BSS",
            team_size=8,
            technologies=["Python", "Kubernetes"],
        )
    )
    await session.commit()


async def _prepare(client: AsyncClient, candidate_id, auth_headers, job_id: str) -> dict:
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


async def test_prepare_requires_existing_match(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    job_ref = await _seed_job(session, candidate.id, "a1")
    await _add_profile_context(session, candidate)
    cid = str(candidate.id)

    resp = await client.post(
        f"/api/v1/candidates/{cid}/applications/jobs/{job_ref['id']}/prepare",
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "Evaluate the job match first" in resp.json()["detail"]


async def test_prepare_creates_application_materials(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    job_ref = await _seed_job(session, candidate.id, "b1")
    await _add_profile_context(session, candidate)
    body = await _prepare(client, candidate.id, auth_headers, job_ref["id"])

    assert body["job_id"] == job_ref["id"]
    assert body["status"] == "draft"
    assert body["match_id"]
    assert body["match_score"] is not None
    assert len(body["questions"]) >= 4
    assert len(body["documents"]) == 3

    types = {doc["doc_type"] for doc in body["documents"]}
    assert types == {"cover_letter", "tailored_resume", "answers_sheet"}
    for doc in body["documents"]:
        assert doc["version_number"] == 1
        assert doc["generation_version"] == "1.0.0"
        assert doc["fact_sources"]

    auto = [q for q in body["questions"] if q["answer"] and q["answer"]["status"] == "auto"]
    assert auto, "expected at least one auto-answerable question"
    for q in auto:
        assert q["answer"]["fact_sources"]
        for source in q["answer"]["fact_sources"]:
            assert source["ref_id"]
            assert source["text"]


async def test_prepare_is_idempotent(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    job_ref = await _seed_job(session, candidate.id, "c1")
    await _add_profile_context(session, candidate)
    first = await _prepare(client, candidate.id, auth_headers, job_ref["id"])
    second = await _prepare(client, candidate.id, auth_headers, job_ref["id"])
    assert first["id"] == second["id"]

    cid = str(candidate.id)
    listing = await client.get(
        f"/api/v1/candidates/{cid}/applications", headers=auth_headers
    )
    assert listing.status_code == 200
    assert len(listing.json()) == 1


async def test_generate_document_creates_new_version(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    job_ref = await _seed_job(session, candidate.id, "d1")
    await _add_profile_context(session, candidate)
    body = await _prepare(client, candidate.id, auth_headers, job_ref["id"])
    app_id = body["id"]
    cid = str(candidate.id)

    resp = await client.post(
        f"/api/v1/candidates/{cid}/applications/{app_id}/documents/generate"
        "?doc_type=cover_letter",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    doc = resp.json()
    assert doc["doc_type"] == "cover_letter"
    assert doc["version_number"] == 2

    listing = await client.get(
        f"/api/v1/candidates/{cid}/applications/{app_id}/documents", headers=auth_headers
    )
    assert listing.status_code == 200
    docs = listing.json()
    assert len(docs) == 4
    cover = [d for d in docs if d["doc_type"] == "cover_letter"]
    assert [d["version_number"] for d in cover] == [1, 2]

    fetched = await client.get(
        f"/api/v1/candidates/{cid}/applications/{app_id}/documents/{doc['id']}",
        headers=auth_headers,
    )
    assert fetched.status_code == 200
    assert fetched.json()["content"]


async def test_update_answer_marks_manual(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    job_ref = await _seed_job(session, candidate.id, "e1")
    await _add_profile_context(session, candidate)
    body = await _prepare(client, candidate.id, auth_headers, job_ref["id"])
    app_id = body["id"]
    cid = str(candidate.id)

    motivation = next(
        q for q in body["questions"] if q["category"] == "motivation"
    )
    question_id = motivation["id"]
    resp = await client.put(
        f"/api/v1/candidates/{cid}/applications/{app_id}/questions/{question_id}/answer",
        json={"answer_text": "I am excited about the product roadmap."},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["answer"]["status"] == "manual"
    assert resp.json()["answer"]["answer_text"] == "I am excited about the product roadmap."

    detail = await client.get(
        f"/api/v1/candidates/{cid}/applications/{app_id}", headers=auth_headers
    )
    assert detail.status_code == 200
    updated = next(
        q for q in detail.json()["questions"] if q["id"] == question_id
    )
    assert updated["answer"]["status"] == "manual"


async def test_update_status_flow(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    job_ref = await _seed_job(session, candidate.id, "f1")
    await _add_profile_context(session, candidate)
    body = await _prepare(client, candidate.id, auth_headers, job_ref["id"])
    app_id = body["id"]
    cid = str(candidate.id)

    resp = await client.post(
        f"/api/v1/candidates/{cid}/applications/{app_id}/status?status=submitted",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "submitted"

    listing = await client.get(
        f"/api/v1/candidates/{cid}/applications", headers=auth_headers
    )
    assert listing.json()[0]["status"] == "submitted"


async def test_cross_candidate_application_is_hidden(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):

    from backend.core.security_service import get_security_service
    from backend.repositories.candidate import CandidateRepository
    from backend.repositories.user import UserRepository

    other_user = await UserRepository(session).create_user(
        "other-prep@example.com", "OtherPass123!"
    )
    other_candidate = await CandidateRepository(session).create_for_user(
        user_id=other_user.id,
        full_name="Other Candidate",
        email="other-prep@example.com",
        headline="Other",
        current_role="Other",
        total_experience_years=4,
    )
    await session.commit()
    other_headers = {
        "Authorization": f"Bearer {get_security_service().create_access_token({'sub': str(other_user.id)})}"
    }

    job_ref = await _seed_job(session, candidate.id, "g1")
    await _add_profile_context(session, candidate)
    body = await _prepare(client, candidate.id, auth_headers, job_ref["id"])
    app_id = body["id"]
    cid = str(candidate.id)
    other_cid = str(other_candidate.id)

    paths = [
        f"/api/v1/candidates/{cid}/applications",
        f"/api/v1/candidates/{cid}/applications/{app_id}",
        f"/api/v1/candidates/{cid}/applications/{app_id}/documents",
    ]
    for path in paths:
        resp = await client.get(path, headers=other_headers)
        assert resp.status_code == 404, f"{path}: {resp.status_code}"

    resp = await client.get(
        f"/api/v1/candidates/{other_cid}/applications", headers=other_headers
    )
    assert resp.status_code == 200
    assert resp.json() == []
