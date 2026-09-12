"""Unit tests for the analytics recommendation guard (Phase 12 fairness)."""

from backend.core.exceptions import ValidationError
from backend.models.learning import RecommendationKind
from backend.services.analytics import (
    PROTECTED_ATTRIBUTE_TERMS,
    AnalyticsService,
    _DraftRecommendation,
)


def _draft(
    *,
    detail: str,
    title: str = "Neutral title",
    rationale: list[str] | None = None,
) -> _DraftRecommendation:
    return _DraftRecommendation(
        kind=RecommendationKind.PROFILE_IMPROVEMENT,
        source_key="test:draft",
        title=title,
        detail=detail,
        rationale=rationale or ["Derived from candidate-owned counts."],
    )


def test_assert_fair_allows_neutral_language() -> None:
    draft = _draft(
        title="Improve your outreach message quality",
        detail=(
            "A manager reviewed outreach messages and reported the response counts "
            "for the latest management dashboard."
        ),
    )
    AnalyticsService._assert_fair([draft])


def test_assert_fair_does_not_trip_on_embedded_words() -> None:
    # "manager", "messages", "management" contain the substring "age" but are
    # not the protected attribute term; token matching must not flag them.
    draft = _draft(
        title="Strengthen your profile",
        detail="Review manager feedback from the latest messages before the next management round.",
    )
    AnalyticsService._assert_fair([draft])


def test_assert_fair_rejects_every_protected_term() -> None:
    for term in PROTECTED_ATTRIBUTE_TERMS:
        draft = _draft(detail=f"Optimize using your {term} instead of neutral signals.")
        try:
            AnalyticsService._assert_fair([draft])
        except ValidationError:
            continue
        raise AssertionError(f"expected {term!r} to be rejected")


def test_assert_fair_rejects_protected_term_case_insensitively() -> None:
    draft = _draft(detail="Consider your Gender when choosing outreach tone.")
    try:
        AnalyticsService._assert_fair([draft])
    except ValidationError:
        pass
    else:
        raise AssertionError("expected 'Gender' to be rejected")


def test_assert_fair_scans_rationale_and_title() -> None:
    title_draft = _draft(title="Race your career onward", detail="All neutral here.")
    rationale_draft = _draft(
        detail="Neutral detail.",
        rationale=["Reported nationality breakdown for the candidate pool."],
    )
    for draft in (title_draft, rationale_draft):
        try:
            AnalyticsService._assert_fair([draft])
        except ValidationError:
            pass
        else:
            raise AssertionError("expected protected attribute in text to be rejected")


def test_protected_attribute_terms_are_defined() -> None:
    assert "gender" in PROTECTED_ATTRIBUTE_TERMS
    assert "age" in PROTECTED_ATTRIBUTE_TERMS
