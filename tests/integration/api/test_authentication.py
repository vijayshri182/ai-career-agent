"""API tests for Authentication & Challenge Management.

Covers provider CRUD, state reporting with automatic challenge creation, the
challenge lifecycle (acknowledge/complete), workflow resume on resolution, and
ownership enforcement for every new sub-resource.
"""

from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

AUTH_URL = "/api/v1/candidates/{candidate_id}/auth"


@pytest_asyncio.fixture
async def foreign_headers(session):
    from backend.core.security_service import get_security_service
    from backend.repositories.user import UserRepository

    repo = UserRepository(session)
    other = await repo.create_user(
        f"auth-foreign-{uuid4().hex[:8]}@example.com", "OtherPass123!"
    )
    await session.commit()
    token = get_security_service().create_access_token({"sub": str(other.id)})
    return {"Authorization": f"Bearer {token}"}


async def _create_provider(client, candidate_id, headers, name="Workday"):
    return await client.post(
        f"{AUTH_URL.format(candidate_id=candidate_id)}/providers",
        json={
            "name": name,
            "provider_type": "ats",
            "base_url": "https://example.workday.com",
            "authentication_method": "password",
            "is_enabled": True,
        },
        headers=headers,
    )


async def test_create_provider(
    client: AsyncClient, candidate, auth_headers: dict
):
    resp = await _create_provider(client, candidate.id, auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Workday"
    assert body["provider_type"] == "ats"
    assert body["authentication_method"] == "password"
    assert body["candidate_id"] == str(candidate.id)
    return body


async def test_duplicate_provider_name_rejected(client, candidate, auth_headers):
    await _create_provider(client, candidate.id, auth_headers)
    resp = await _create_provider(client, candidate.id, auth_headers)
    assert resp.status_code == 400


async def test_list_providers(client, candidate, auth_headers):
    await _create_provider(client, candidate.id, auth_headers, name="Greenhouse")
    resp = await client.get(
        f"{AUTH_URL.format(candidate_id=candidate.id)}/providers", headers=auth_headers
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_initial_state_not_configured(client, candidate, auth_headers):
    provider = (await _create_provider(client, candidate.id, auth_headers)).json()
    resp = await client.get(
        f"{AUTH_URL.format(candidate_id=candidate.id)}/providers/{provider['id']}/state",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "not_configured"


async def test_update_provider(client, candidate, auth_headers):
    provider = (await _create_provider(client, candidate.id, auth_headers)).json()
    resp = await client.put(
        f"{AUTH_URL.format(candidate_id=candidate.id)}/providers/{provider['id']}",
        json={"is_enabled": False, "notes": "deprecated"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_enabled"] is False
    assert body["notes"] == "deprecated"


async def test_report_captcha_creates_challenge(client, candidate, auth_headers):
    provider = (await _create_provider(client, candidate.id, auth_headers)).json()
    base = AUTH_URL.format(candidate_id=candidate.id)
    resp = await client.post(
        f"{base}/providers/{provider['id']}/state",
        json={"status": "captcha_required", "metadata": {"snippet": "recaptcha"}},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "captcha_required"

    challenges = await client.get(f"{base}/challenges", headers=auth_headers)
    assert challenges.status_code == 200
    data = challenges.json()
    assert len(data) == 1
    assert data[0]["challenge_type"] == "captcha"
    assert data[0]["status"] == "open"

    outstanding = await client.get(f"{base}/challenges/outstanding", headers=auth_headers)
    assert outstanding.status_code == 200
    assert len(outstanding.json()) == 1


async def test_repeat_report_is_idempotent(client, candidate, auth_headers):
    provider = (await _create_provider(client, candidate.id, auth_headers)).json()
    base = AUTH_URL.format(candidate_id=candidate.id)
    state_url = f"{base}/providers/{provider['id']}/state"
    await client.post(
        state_url, json={"status": "captcha_required"}, headers=auth_headers
    )
    await client.post(
        state_url, json={"status": "captcha_required"}, headers=auth_headers
    )
    challenges = await client.get(f"{base}/challenges", headers=auth_headers)
    assert len(challenges.json()) == 1


async def test_challenge_lifecycle_and_workflow_resume(
    client: AsyncClient, candidate, auth_headers: dict
):
    provider = (await _create_provider(client, candidate.id, auth_headers)).json()
    base = AUTH_URL.format(candidate_id=candidate.id)

    await client.post(
        f"{base}/providers/{provider['id']}/state",
        json={"status": "captcha_required"},
        headers=auth_headers,
    )
    challenge = (await client.get(f"{base}/challenges", headers=auth_headers)).json()[0]

    ack = await client.post(
        f"{base}/challenges/{challenge['id']}/acknowledge", headers=auth_headers
    )
    assert ack.status_code == 200
    assert ack.json()["status"] == "acknowledged"

    done = await client.post(
        f"{base}/challenges/{challenge['id']}/complete",
        json={"resolution_method": "human", "notes": "completed in browser"},
        headers=auth_headers,
    )
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == "resolved"
    assert body["resolution_method"] == "human"

    state = await client.get(
        f"{base}/providers/{provider['id']}/state", headers=auth_headers
    )
    assert state.json()["status"] == "authenticated"


async def test_cross_user_returns_404(client, candidate, foreign_headers):
    base = AUTH_URL.format(candidate_id=candidate.id)
    assert (
        await client.get(f"{base}/overview", headers=foreign_headers)
    ).status_code == 404
    assert (
        await client.get(f"{base}/providers", headers=foreign_headers)
    ).status_code == 404
    assert (
        await _create_provider(client, candidate.id, foreign_headers)
    ).status_code == 404
    assert (
        await client.get(f"{base}/challenges", headers=foreign_headers)
    ).status_code == 404
    assert (
        await client.get(f"{base}/secrets", headers=foreign_headers)
    ).status_code == 404
    assert (
        await client.get(f"{base}/browser-sessions", headers=foreign_headers)
    ).status_code == 404


async def test_provider_crud_operations(client, candidate, auth_headers):
    provider = (await _create_provider(client, candidate.id, auth_headers)).json()
    base = AUTH_URL.format(candidate_id=candidate.id)
    resp = await client.get(
        f"{base}/providers/{provider['id']}", headers=auth_headers
    )
    assert resp.status_code == 200
    delete = await client.delete(
        f"{base}/providers/{provider['id']}", headers=auth_headers
    )
    assert delete.status_code == 204
    assert (
        await client.get(f"{base}/providers/{provider['id']}", headers=auth_headers)
    ).status_code == 404
