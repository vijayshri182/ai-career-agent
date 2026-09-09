"""apply-parsed must populate the candidate profile from extracted data."""

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


async def _create_candidate(client: AsyncClient, auth_headers: dict) -> str:
    r = await client.post(
        "/api/v1/candidates",
        json={
            "full_name": "Original Name",
            "email": "original@example.com",
            "headline": "Original Headline",
        },
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _upload_and_parse(
    client: AsyncClient, auth_headers: dict, candidate_id: str
) -> str:
    r = await client.post(
        f"/api/v1/candidates/{candidate_id}/resumes",
        json={"name": "Main Resume", "resume_type": "general"},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    resume_id = r.json()["id"]

    content, ctype = _docx_bytes(
        "Jane Doe\njane.doe@example.com\nJava Spring Boot Kubernetes\n"
    )
    r = await client.post(
        f"/api/v1/candidates/{candidate_id}/resumes/{resume_id}/upload",
        files={"file": ("resume.docx", content, ctype)},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text

    r = await client.post(
        f"/api/v1/candidates/{candidate_id}/resumes/{resume_id}/parse",
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["extracted_data"]["email"] == "jane.doe@example.com"
    return resume_id


async def test_apply_parsed_populates_profile(
    client: AsyncClient, auth_headers: dict
):
    candidate_id = await _create_candidate(client, auth_headers)
    resume_id = await _upload_and_parse(client, auth_headers, candidate_id)

    r = await client.post(
        f"/api/v1/candidates/{candidate_id}/resumes/{resume_id}/apply-parsed?confirm=true",
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "applied"

    r = await client.get("/api/v1/candidates/me", headers=auth_headers)
    assert r.status_code == 200
    profile = r.json()
    assert profile["email"] == "jane.doe@example.com"
    assert profile["full_name"] == "Original Name"
    assert profile["headline"] == "Original Headline"

    r = await client.get(f"/api/v1/candidates/{candidate_id}/skills", headers=auth_headers)
    assert r.status_code == 200
    assert {skill["name"] for skill in r.json()} == {"Java", "Spring Boot", "Kubernetes"}


async def test_apply_parsed_is_idempotent_for_skills(
    client: AsyncClient, auth_headers: dict
):
    candidate_id = await _create_candidate(client, auth_headers)
    resume_id = await _upload_and_parse(client, auth_headers, candidate_id)
    apply_url = f"/api/v1/candidates/{candidate_id}/resumes/{resume_id}/apply-parsed?confirm=true"

    assert (
        await client.post(apply_url, headers=auth_headers)
    ).status_code == 200
    assert (
        await client.post(apply_url, headers=auth_headers)
    ).status_code == 200

    r = await client.get(f"/api/v1/candidates/{candidate_id}/skills", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 3


async def test_apply_parsed_confirm_false_is_rejected_without_mutation(
    client: AsyncClient, auth_headers: dict
):
    candidate_id = await _create_candidate(client, auth_headers)
    resume_id = await _upload_and_parse(client, auth_headers, candidate_id)

    r = await client.post(
        f"/api/v1/candidates/{candidate_id}/resumes/{resume_id}/apply-parsed?confirm=false",
        headers=auth_headers,
    )
    assert r.status_code == 400

    r = await client.get("/api/v1/candidates/me", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["email"] == "original@example.com"

    r = await client.get(
        f"/api/v1/candidates/{candidate_id}/resumes/{resume_id}/parse",
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "pending"


async def test_apply_parsed_omitted_confirm_is_rejected_without_mutation(
    client: AsyncClient, auth_headers: dict
):
    candidate_id = await _create_candidate(client, auth_headers)
    resume_id = await _upload_and_parse(client, auth_headers, candidate_id)

    r = await client.post(
        f"/api/v1/candidates/{candidate_id}/resumes/{resume_id}/apply-parsed",
        headers=auth_headers,
    )
    assert r.status_code == 400

    r = await client.get("/api/v1/candidates/me", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["email"] == "original@example.com"

    r = await client.get(
        f"/api/v1/candidates/{candidate_id}/resumes/{resume_id}/parse",
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "pending"


async def test_apply_parsed_preserves_manual_edit_on_reapply(
    client: AsyncClient, auth_headers: dict
):
    candidate_id = await _create_candidate(client, auth_headers)
    resume_id = await _upload_and_parse(client, auth_headers, candidate_id)
    apply_url = f"/api/v1/candidates/{candidate_id}/resumes/{resume_id}/apply-parsed?confirm=true"

    r = await client.post(apply_url, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "applied"

    r = await client.put(
        f"/api/v1/candidates/{candidate_id}",
        json={"email": "manual-edit@example.com"},
        headers=auth_headers,
    )
    assert r.status_code == 200

    r = await client.post(apply_url, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "applied"

    r = await client.get("/api/v1/candidates/me", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["email"] == "manual-edit@example.com"

    r = await client.get(f"/api/v1/candidates/{candidate_id}/skills", headers=auth_headers)
    assert r.status_code == 200
    assert {skill["name"] for skill in r.json()} == {"Java", "Spring Boot", "Kubernetes"}
