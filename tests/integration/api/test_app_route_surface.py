"""API-surface contract test.

Asserts that the FastAPI app registered by ``backend.app.main`` exposes the
documented routes (see ``docs/api/api-overview.md``) and that no invented,
undocumented routes are mounted. Guards against unwired routers and phantom
routes. Introspection uses ``app.openapi()`` so mounted routers
(FastAPI 0.141 ``_IncludedRouter``) are covered.
"""

from backend.app.main import app


def _openapi_paths() -> dict[str, dict]:
    return app.openapi()["paths"]


def _methods_for(path: str) -> set[str]:
    methods = _openapi_paths().get(path, {})
    return {m.upper() for m in methods}


def test_health_and_readiness_are_registered() -> None:
    assert "GET" in _methods_for("/health")
    assert "GET" in _methods_for("/ready")


def test_documented_route_surface_is_mounted() -> None:
    expected = {
        "/api/v1/auth/register": {"POST"},
        "/api/v1/auth/login": {"POST"},
        "/api/v1/auth/me": {"GET"},
        "/api/v1/candidates/{candidate_id}/audit-events": {"GET"},
        "/api/v1/candidates/{candidate_id}/dashboard/summary": {"GET"},
        "/api/v1/candidates/{candidate_id}/discovery-runs": {"POST", "GET"},
        "/api/v1/candidates/{candidate_id}/automation/status": {"GET"},
        "/api/v1/candidates/{candidate_id}/automation/runs": {"GET"},
        "/api/v1/candidates/{candidate_id}/notifications": {"GET"},
        "/api/v1/candidates/{candidate_id}/notifications/unread-count": {"GET"},
        "/api/v1/candidates/{candidate_id}/notifications/read-all": {"POST"},
        "/api/v1/candidates/{candidate_id}/notifications/preferences": {"GET", "PUT"},
        "/api/v1/candidates/{candidate_id}/applications/jobs/{job_id}/prepare": {"POST"},
        "/api/v1/candidates/{candidate_id}/matching/evaluate": {"POST"},
        "/api/v1/candidates/{candidate_id}/outreach/drafts": {"POST"},
        "/api/v1/candidates/{candidate_id}/recruiter-contacts": {"GET"},
        "/api/v1/candidates/{candidate_id}/jobs/{job_id}/discover-contacts": {"POST"},
        "/api/v1/candidates/{candidate_id}/approvals": {"GET"},
        "/api/v1/candidates/{candidate_id}/analytics/summary": {"GET"},
        "/api/v1/candidates/{candidate_id}/recommendations": {"GET"},
        "/api/v1/candidates/{candidate_id}/auth/challenges": {"GET"},
        "/api/v1/candidates/{candidate_id}/job-sources": {"GET", "POST"},
    }
    for path, methods in expected.items():
        assert _methods_for(path) >= methods, f"route {path} missing methods {methods}"


def test_profile_areas_are_mounted() -> None:
    areas = {
        "/api/v1/candidates": {"POST"},
        "/api/v1/candidates/{candidate_id}": {"GET"},
        "/api/v1/candidates/{candidate_id}/profile": {"GET"},
        "/api/v1/candidates/{candidate_id}/skills": {"GET", "POST"},
        "/api/v1/candidates/{candidate_id}/experience": {"GET", "POST"},
        "/api/v1/candidates/{candidate_id}/education": {"GET", "POST"},
        "/api/v1/candidates/{candidate_id}/certifications": {"GET", "POST"},
        "/api/v1/candidates/{candidate_id}/resumes": {"GET", "POST"},
        "/api/v1/candidates/{candidate_id}/jobs": {"GET"},
    }
    for path, methods in areas.items():
        assert _methods_for(path) >= methods, f"area {path} missing methods {methods}"


def test_no_undocumented_agent_tasks_route_is_invented() -> None:
    assert "/api/v1/candidates/{candidate_id}/agent-tasks" not in _openapi_paths()


def test_openapi_served_and_titles_app() -> None:
    info = app.openapi()["info"]
    assert info["title"] == "AI Career Agent"
    assert app.docs_url == "/api/docs"
    assert app.openapi_url == "/api/openapi.json"
