"""Unit tests for the extraction-to-profile mapping used by apply-parsed."""

import pytest

from backend.services.resume import ResumeService


def _map(extracted: dict[str, object]) -> dict[str, object]:
    return ResumeService._profile_fields_from_extraction(extracted)


def test_maps_all_phase1_fields() -> None:
    extracted: dict[str, object] = {
        "name": "  VIJAY SHRIVASTAVA  ",
        "email": "vijayshri182@gmail.com",
        "phone": "+91 9148975538",
        "headline": "Engineering Leader | Telecom BSS/OSS",
        "current_role": "Senior Technical Manager",
        "summary": "Line one\nLine two",
        "total_experience_years": 20,
        "current_location": {"city": "Bangalore", "country": None},
        "raw_text": "full text here",
        "skills": ["Java", "Kubernetes"],
    }
    assert _map(extracted) == {
        "full_name": "VIJAY SHRIVASTAVA",
        "email": "vijayshri182@gmail.com",
        "phone": "+91 9148975538",
        "headline": "Engineering Leader | Telecom BSS/OSS",
        "current_role": "Senior Technical Manager",
        "summary": "Line one\nLine two",
        "total_experience_years": 20,
        "current_location": {"city": "Bangalore", "country": None},
    }


def test_skips_blank_and_none_fields() -> None:
    extracted: dict[str, object] = {
        "name": "   ",
        "email": "",
        "phone": None,
        "headline": None,
        "current_role": None,
        "summary": "",
        "total_experience_years": 0,
        "current_location": {},
    }
    assert _map(extracted) == {}


def test_skills_and_raw_text_are_not_profile_fields() -> None:
    extracted: dict[str, object] = {
        "name": "Jane Doe",
        "skills": ["Java"],
        "raw_text": "raw",
    }
    result = _map(extracted)
    assert result == {"full_name": "Jane Doe"}
    assert "skills" not in result
    assert "raw_text" not in result


def test_rejects_malformed_years_and_location() -> None:
    for value in (None, 0, -3, "20", 20.0):
        assert _map({"total_experience_years": value}) == {}, value
    for value in (None, {}, {"city": ""}, {"city": None, "country": None}, "Bangalore"):
        assert _map({"current_location": value}) == {}, value


def test_accepts_location_with_any_non_empty_component() -> None:
    assert _map({"current_location": {"country": "India"}}) == {
        "current_location": {"country": "India"}
    }


def test_current_location_is_copied_not_aliased() -> None:
    location = {"city": "Bangalore", "country": "India"}
    result = _map({"current_location": location})
    assert result == {"current_location": {"city": "Bangalore", "country": "India"}}
    location["city"] = "Mumbai"
    assert result["current_location"] == {"city": "Bangalore", "country": "India"}


@pytest.mark.parametrize(
    "value",
    [
        "Engineering Leader",
        # Unicode whitespace still counts as a stripped value.
        "\u2003 Lead Engineer \u2003",
    ],
)
def test_string_fields_are_stripped(value: str) -> None:
    assert _map({"headline": value}) == {"headline": value.strip()}
