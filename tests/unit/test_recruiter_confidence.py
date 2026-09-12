"""Unit tests for the recruiter confidence scorer."""

from backend.models.recruiter_contact import ContactType
from backend.services.recruiter_confidence import (
    AffiliationConfidenceScorer,
    is_recruiting_role,
)


def _scorer() -> AffiliationConfidenceScorer:
    return AffiliationConfidenceScorer()


def test_recruiting_role_keywords():
    assert is_recruiting_role("Technical Recruiter")
    assert is_recruiting_role("Senior Talent Acquisition Partner")
    assert is_recruiting_role("Head of People Operations")
    assert not is_recruiting_role("Senior Software Engineer")
    assert not is_recruiting_role("Product Manager")


def test_verified_contact_on_company_domain_is_surfaced():
    result = _scorer().score(
        role_title="Talent Acquisition Recruiter",
        on_company_domain=True,
        has_public_profile_url=True,
    )
    assert result.score == 95
    assert result.contact_type == ContactType.VERIFIED
    assert result.surfaced is True


def test_exact_threshold_70_surfaces_verified_contact():
    result = _scorer().score(
        role_title="People Partner",
        on_company_domain=True,
        has_public_profile_url=False,
        email_publicly_listed=True,
    )
    assert result.score == 70
    assert result.contact_type == ContactType.VERIFIED
    assert result.surfaced is True


def test_below_threshold_never_surfaces():
    result = _scorer().score(
        role_title="People Partner",
        on_company_domain=True,
        has_public_profile_url=False,
        email_publicly_listed=False,
    )
    assert result.score == 65
    assert result.contact_type == ContactType.VERIFIED
    assert result.surfaced is False


def test_company_domain_required_for_verified():
    result = _scorer().score(
        role_title="Recruiter",
        on_company_domain=False,
        has_public_profile_url=True,
    )
    assert result.contact_type == ContactType.GUESSED
    assert result.surfaced is False


def test_recruiting_role_required_for_verified_even_on_domain():
    result = _scorer().score(
        role_title="Senior Software Engineer",
        on_company_domain=True,
        has_public_profile_url=True,
    )
    assert result.contact_type == ContactType.GUESSED
    assert result.surfaced is False


def test_score_is_clamped_to_100():
    result = _scorer().score(
        role_title="Talent Acquisition Recruiter",
        on_company_domain=True,
        has_public_profile_url=True,
        email_publicly_listed=True,
    )
    assert result.score == 100


def test_email_bonus_flags_public_listing_only():
    listed = _scorer().score(
        role_title="Recruiter",
        on_company_domain=True,
        has_public_profile_url=False,
        email_publicly_listed=True,
    )
    unlisted = _scorer().score(
        role_title="Recruiter",
        on_company_domain=True,
        has_public_profile_url=False,
        email_publicly_listed=False,
    )
    assert listed.score == 70 and listed.surfaced is True
    assert unlisted.score == 65 and unlisted.surfaced is False


def test_unverifiable_contact_carries_reasons():
    result = _scorer().score(
        role_title="Recruiter at Unknown Firm",
        on_company_domain=False,
        has_public_profile_url=False,
    )
    assert result.surfaced is False
    assert any("not verified" in reason for reason in result.reasons)
