"""Integration tests for the job matching API (deterministic engine)."""

from datetime import UTC, date, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _seed_job(session: AsyncSession, candidate_id, cid) -> dict:
    from backend.models.company import Company
    from backend.repositories.company import CompanyRepository
    from backend.repositories.job import JobRepository
    from backend.repositories.job_source import JobSourceRepository

    company = await CompanyRepository(session).get_or_create_by_domain(
        name="Acme Networks", domain="acme.test"
    )
    assert isinstance(company, Company)
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
            "- Preferred: AWS\n"
            "Telecom BSS background is a plus."
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
            domain="Telecom BSS",
            team_size=8,
        )
    )
    await session.commit()


async def test_evaluate_job_endpoint(client: AsyncClient, candidate, auth_headers, session: AsyncSession):
    job_ref = await _seed_job(session, candidate.id, "e1")
    await _add_profile_context(session, candidate)
    cid = str(candidate.id)

    resp = await client.post(f"/api/v1/candidates/{cid}/jobs/{job_ref['id']}/match", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["is_match"] is True
    assert data["score"] >= 70
    assert "Python" in data["matched_skills"]
    assert data["rules_version"]
    assert data["evaluated_at"]
    assert "components" in data["score_breakdown"]
    assert "weights" in data["score_breakdown"]


async def test_evaluation_is_idempotent(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    job_ref = await _seed_job(session, candidate.id, "i1")
    await _add_profile_context(session, candidate)
    cid = str(candidate.id)

    first = (await client.post(f"/api/v1/candidates/{cid}/jobs/{job_ref['id']}/match", headers=auth_headers)).json()
    second = (await client.post(f"/api/v1/candidates/{cid}/jobs/{job_ref['id']}/match", headers=auth_headers)).json()
    assert first["id"] == second["id"]
    assert first["score"] == second["score"]

    matches = (await client.get(f"/api/v1/candidates/{cid}/matches", headers=auth_headers)).json()
    assert matches["total"] == 1


async def test_list_matches_filters_and_sorts(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    job_ref = await _seed_job(session, candidate.id, "f1")
    await _add_profile_context(session, candidate)
    cid = str(candidate.id)
    await client.post(f"/api/v1/candidates/{cid}/jobs/{job_ref['id']}/match", headers=auth_headers)

    resp = await client.get(
        f"/api/v1/candidates/{cid}/matches?is_match=true&min_score=50", headers=auth_headers
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["total"] == 1
    assert body["items"][0]["job_id"] == job_ref["id"]

    bad = await client.get(
        f"/api/v1/candidates/{cid}/matches?is_match=false", headers=auth_headers
    )
    assert bad.json()["total"] == 0

    fetched = await client.get(
        f"/api/v1/candidates/{cid}/jobs/{job_ref['id']}/match", headers=auth_headers
    )
    assert fetched.status_code == 200
    assert fetched.json()["is_match"] is True


async def test_batch_evaluate_endpoint(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    await _seed_job(session, candidate.id, "b1")
    await _seed_job(session, candidate.id, "b2")
    await _add_profile_context(session, candidate)
    cid = str(candidate.id)

    resp = await client.post(f"/api/v1/candidates/{cid}/matching/evaluate", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["evaluated"] == 2
    assert body["errors"] == 0
    assert body["matched"] >= 1


async def test_expired_job_match_still_supported(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    job_ref = await _seed_job(session, candidate.id, "x1")
    await _add_profile_context(session, candidate)
    cid = str(candidate.id)

    resp = await client.get(f"/api/v1/candidates/{cid}/jobs/{job_ref['id']}/match", headers=auth_headers)
    assert resp.status_code == 404
