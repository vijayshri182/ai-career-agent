"""Ownership enforcement for candidate sub-resources.

A user must not be able to list, create, read, update, or delete
sub-resources (skills, experience, education, certifications, resumes)
of a candidate that is not theirs. Cross-user and non-existent
candidates are indistinguishable and both return 404.
"""

from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def other_headers(session):
    from backend.core.security_service import get_security_service
    from backend.repositories.user import UserRepository

    repo = UserRepository(session)
    other = await repo.create_user(f"other-{uuid4().hex[:8]}@example.com", "OtherPass123!")
    await session.commit()
    token = get_security_service().create_access_token({"sub": str(other.id)})
    return {"Authorization": f"Bearer {token}"}


async def test_cross_user_skills_return_404(
    client: AsyncClient, candidate, other_headers: dict
):
    url = f"/api/v1/candidates/{candidate.id}/skills"
    assert (await client.get(url, headers=other_headers)).status_code == 404
    assert (
        await client.post(url, json={"name": "Java"}, headers=other_headers)
    ).status_code == 404


async def test_cross_user_experience_return_404(
    client: AsyncClient, candidate, other_headers: dict
):
    url = f"/api/v1/candidates/{candidate.id}/experience"
    assert (await client.get(url, headers=other_headers)).status_code == 404
    assert (
        await client.post(
            url,
            json={"company_name": "Corp", "title": "Eng", "start_date": "2020-01-01"},
            headers=other_headers,
        )
    ).status_code == 404


async def test_cross_user_education_return_404(
    client: AsyncClient, candidate, other_headers: dict
):
    url = f"/api/v1/candidates/{candidate.id}/education"
    assert (await client.get(url, headers=other_headers)).status_code == 404
    assert (
        await client.post(
            url,
            json={"institution": "Uni", "degree": "B.Sc"},
            headers=other_headers,
        )
    ).status_code == 404


async def test_cross_user_certifications_return_404(
    client: AsyncClient, candidate, other_headers: dict
):
    url = f"/api/v1/candidates/{candidate.id}/certifications"
    assert (await client.get(url, headers=other_headers)).status_code == 404
    assert (
        await client.post(
            url,
            json={"name": "AWS Certified"},
            headers=other_headers,
        )
    ).status_code == 404


async def test_cross_user_resumes_return_404(
    client: AsyncClient, candidate, other_headers: dict
):
    url = f"/api/v1/candidates/{candidate.id}/resumes"
    assert (await client.get(url, headers=other_headers)).status_code == 404
    assert (
        await client.post(
            url,
            json={"name": "Secret Resume", "resume_type": "general"},
            headers=other_headers,
        )
    ).status_code == 404


async def test_owner_can_update_and_delete_owned_subresource(
    client: AsyncClient, candidate, auth_headers: dict, other_headers: dict
):
    r = await client.post(
        f"/api/v1/candidates/{candidate.id}/skills",
        json={"name": "Python"},
        headers=auth_headers,
    )
    assert r.status_code == 201
    skill_id = r.json()["id"]
    url = f"/api/v1/candidates/{candidate.id}/skills/{skill_id}"

    assert (
        await client.put(url, json={"proficiency": "advanced"}, headers=other_headers)
    ).status_code == 404
    assert (await client.delete(url, headers=other_headers)).status_code == 404

    r = await client.put(url, json={"proficiency": "advanced"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["proficiency"] == "advanced"

    assert (await client.delete(url, headers=auth_headers)).status_code == 204


async def test_non_existent_candidate_resources_return_404(
    client: AsyncClient, auth_headers: dict
):
    url = f"/api/v1/candidates/{uuid4()}/skills"
    assert (await client.get(url, headers=auth_headers)).status_code == 404
    assert (
        await client.post(url, json={"name": "Java"}, headers=auth_headers)
    ).status_code == 404
