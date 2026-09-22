"""Integration tests for the audit trail read API."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def test_audit_events_listing(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    from backend.repositories.audit import AuditRepository

    cid = str(candidate.id)
    audit = AuditRepository(session)
    await audit.log("test.event.one", actor_id=candidate.user_id, candidate_id=candidate.id)
    await audit.log(
        "test.event.two",
        actor_id=candidate.user_id,
        candidate_id=candidate.id,
        metadata={"tube": "zebra"},
    )
    await session.commit()

    resp = await client.get(f"/api/v1/candidates/{cid}/audit-events", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    event_types = {item["event_type"] for item in body["items"]}
    assert event_types == {"test.event.one", "test.event.two"}
    assert body["items"][0]["candidate_id"] == cid
    assert body["items"][0]["result"] == "success"

    filtered = await client.get(
        f"/api/v1/candidates/{cid}/audit-events?event_type=test.event.two",
        headers=auth_headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["event_metadata"]["tube"] == "zebra"

    limited = await client.get(
        f"/api/v1/candidates/{cid}/audit-events?limit=1&offset=1", headers=auth_headers
    )
    assert limited.status_code == 200
    assert limited.json()["total"] == 2
    assert len(limited.json()["items"]) == 1


async def test_audit_events_cross_user_hidden(
    client: AsyncClient, candidate, auth_headers, session: AsyncSession
):
    from backend.core.security_service import get_security_service
    from backend.repositories.audit import AuditRepository
    from backend.repositories.user import UserRepository

    other_user = await UserRepository(session).create_user("other-audit@example.com", "OtherPass123!")
    await session.commit()
    other_headers = {
        "Authorization": (
            f"Bearer {get_security_service().create_access_token({'sub': str(other_user.id)})}"
        )
    }

    cid = str(candidate.id)
    await AuditRepository(session).log(
        "test.event.one", actor_id=candidate.user_id, candidate_id=candidate.id
    )
    await session.commit()

    resp = await client.get(
        f"/api/v1/candidates/{cid}/audit-events", headers=other_headers
    )
    assert resp.status_code == 404


async def test_audit_events_require_auth(
    client: AsyncClient, candidate
):
    cid = str(candidate.id)
    resp = await client.get(f"/api/v1/candidates/{cid}/audit-events")
    assert resp.status_code == 401
