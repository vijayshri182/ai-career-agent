"""Integration test for candidate profile end-to-end flow."""

from io import BytesIO

import pytest
from docx import Document
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


def _docx_bytes(text: str) -> tuple[bytes, str]:
    doc = Document()
    doc.add_paragraph(text)
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


async def test_register_and_login(client: AsyncClient):
    r = await client.post("/api/v1/auth/register", json={
        "email": "newuser@example.com",
        "password": "StrongP@ssw0rd!",
    })
    assert r.status_code == 201
    token = r.json()["access_token"]
    assert token

    r = await client.post("/api/v1/auth/login", json={
        "email": "newuser@example.com",
        "password": "StrongP@ssw0rd!",
    })
    assert r.status_code == 200
    assert "access_token" in r.json()


async def test_unauthorized_request(client: AsyncClient):
    r = await client.get("/api/v1/candidates/me")
    assert r.status_code == 401


async def test_create_and_get_candidate(client: AsyncClient, auth_headers: dict):
    r = await client.post("/api/v1/candidates", json={
        "full_name": "Vijay Shrivastava",
        "email": "vijay@example.com",
        "headline": "Technology Leader",
        "current_role": "Senior Engineering Manager",
        "target_role": "Engineering Director",
        "total_experience_years": 18,
        "notice_period_days": 60,
        "work_mode_preference": "hybrid",
    }, headers=auth_headers)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["full_name"] == "Vijay Shrivastava"
    assert data["email"] == "vijay@example.com"

    r = await client.get("/api/v1/candidates/me", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["full_name"] == "Vijay Shrivastava"


async def test_update_candidate(client: AsyncClient, candidate, auth_headers: dict):
    r = await client.put(f"/api/v1/candidates/{candidate.id}", json={
        "headline": "Updated headline",
        "summary": "New summary",
    }, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["headline"] == "Updated headline"
    assert r.json()["summary"] == "New summary"


async def test_skill_crud(client: AsyncClient, candidate, auth_headers: dict):
    r = await client.post(f"/api/v1/candidates/{candidate.id}/skills", json={
        "name": "Spring Boot",
        "category": "framework",
        "proficiency": "expert",
        "years_experience": 10,
        "is_primary": True,
    }, headers=auth_headers)
    assert r.status_code == 201
    skill = r.json()
    assert skill["name"] == "Spring Boot"

    r = await client.get(f"/api/v1/candidates/{candidate.id}/skills", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 1

    r = await client.put(f"/api/v1/candidates/{candidate.id}/skills/{skill['id']}", json={
        "proficiency": "intermediate",
    }, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["proficiency"] == "intermediate"

    r = await client.delete(
        f"/api/v1/candidates/{candidate.id}/skills/{skill['id']}", headers=auth_headers
    )
    assert r.status_code == 204


async def test_experience_crud(client: AsyncClient, candidate, auth_headers: dict):
    r = await client.post(f"/api/v1/candidates/{candidate.id}/experience", json={
        "company_name": "Example Corp",
        "title": "Senior Manager",
        "start_date": "2015-06-01",
        "is_current": True,
        "responsibilities": [" Led team"],
        "achievements": ["Delivered project"],
    }, headers=auth_headers)
    assert r.status_code == 201
    exp = r.json()
    assert exp["company_name"] == "Example Corp"
    assert exp["responsibilities"] == [" Led team"]
    assert exp["achievements"] == ["Delivered project"]

    r = await client.delete(
        f"/api/v1/candidates/{candidate.id}/experience/{exp['id']}", headers=auth_headers
    )
    assert r.status_code == 204


async def test_education_crud(client: AsyncClient, candidate, auth_headers: dict):
    r = await client.post(f"/api/v1/candidates/{candidate.id}/education", json={
        "institution": "University",
        "degree": "B.Tech",
        "field_of_study": "Computer Science",
        "start_date": "2001-08-01",
        "end_date": "2005-05-01",
    }, headers=auth_headers)
    assert r.status_code == 201

    r = await client.get(f"/api/v1/candidates/{candidate.id}/education", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 1


async def test_certification_crud(client: AsyncClient, candidate, auth_headers: dict):
    r = await client.post(f"/api/v1/candidates/{candidate.id}/certifications", json={
        "name": "AWS Solutions Architect",
        "issuing_organization": "AWS",
        "issue_date": "2020-01-01",
    }, headers=auth_headers)
    assert r.status_code == 201


async def test_preferences_and_profile(client: AsyncClient, candidate, auth_headers: dict):
    r = await client.put(f"/api/v1/candidates/{candidate.id}/preferences", json={
        "target_roles": ["Engineering Manager", "Technical Architect"],
        "preferred_locations": ["Bangalore", "Remote"],
        "work_mode": "hybrid",
        "min_compensation": 5000000,
        "target_compensation": 7000000,
        "employment_type": "full_time",
    }, headers=auth_headers)
    assert r.status_code == 200

    r = await client.get(f"/api/v1/candidates/{candidate.id}/profile", headers=auth_headers)
    assert r.status_code == 200
    profile = r.json()
    assert profile["candidate"]["id"] == str(candidate.id)
    assert "completeness" in profile
    assert profile["completeness"]["percentage"] >= 0


async def test_resume_upload_parse_and_apply(client: AsyncClient, candidate, auth_headers: dict):
    # Create resume container
    r = await client.post(f"/api/v1/candidates/{candidate.id}/resumes", json={
        "name": "Main Resume",
        "resume_type": "general",
    }, headers=auth_headers)
    assert r.status_code == 201
    resume_id = r.json()["id"]

    content, ctype = _docx_bytes(
        "Jane Doe\njane.doe@example.com\nJava Spring Boot Kubernetes\n"
    )
    r = await client.post(
        f"/api/v1/candidates/{candidate.id}/resumes/{resume_id}/upload",
        files={"file": ("resume.docx", content, ctype)},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    version = r.json()
    assert version["original_filename"] == "resume.docx"

    r = await client.post(
        f"/api/v1/candidates/{candidate.id}/resumes/{resume_id}/parse",
        headers=auth_headers,
    )
    assert r.status_code == 200
    parsed = r.json()
    assert parsed["extracted_data"]["email"] == "jane.doe@example.com"

    r = await client.get(
        f"/api/v1/candidates/{candidate.id}/resumes/{resume_id}/parse",
        headers=auth_headers,
    )
    assert r.status_code == 200

    r = await client.post(
        f"/api/v1/candidates/{candidate.id}/resumes/{resume_id}/apply-parsed?confirm=true",
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "applied"


async def test_unauthorized_cross_candidate_access(client: AsyncClient, candidate, session):
    from backend.repositories.user import UserRepository

    other = await UserRepository(session).create_user("other@example.com", "OtherPass123!")
    await session.commit()

    from backend.core.security_service import get_security_service

    token = get_security_service().create_access_token({"sub": str(other.id)})
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get(f"/api/v1/candidates/{candidate.id}", headers=headers)
    assert r.status_code == 404


async def test_invalid_upload_rejected(client: AsyncClient, candidate, auth_headers: dict):
    r = await client.post(
        f"/api/v1/candidates/{candidate.id}/resumes/upload",
        files={"file": ("malware.exe", b"MZ", "application/x-msdownload")},
        headers=auth_headers,
    )
    assert r.status_code == 400
