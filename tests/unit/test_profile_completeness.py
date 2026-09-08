"""Profile completeness tests."""

from backend.core.config import Settings
from backend.core.security_service import get_security_service
from backend.models.candidate import Candidate
from backend.services.completeness import ProfileCompletenessService


def _candidate(**kwargs):
    defaults = {
        "full_name": "Name",
        "headline": "Headline",
        "email_encrypted": get_security_service().encrypt("a@b.com"),
        "current_role": "Lead",
    }
    defaults.update(kwargs)
    return Candidate(**defaults)


def test_empty_profile_has_low_score():
    service = ProfileCompletenessService()
    candidate = Candidate()
    result = service.calculate(candidate, [], [], [], [], [])
    assert result["percentage"] < 30


def test_full_profile_reaches_high_score():
    service = ProfileCompletenessService()
    candidate = _candidate(
        summary="summary",
        career_preferences={
            "target_roles": ["Manager"],
            "preferred_locations": ["India"],
            "work_mode": "remote",
        },
    )
    result = service.calculate(
        candidate,
        skills=[object()],
        experiences=[object()],  # type: ignore[list-item]
        educations=[object()],  # type: ignore[list-item]
        certifications=[object()],  # type: ignore[list-item]
        resumes=[object()],  # type: ignore[list-item]
    )
    assert result["percentage"] >= 90


def test_custom_weights_applied():
    service = ProfileCompletenessService(Settings(profile_completeness_weights="basic=50,summary=50"))
    assert service.maximum == 100
    candidate = _candidate(summary="summary")
    result = service.calculate(candidate, [], [], [], [], [])
    assert result["total"] == 100
    assert result["percentage"] == 100
