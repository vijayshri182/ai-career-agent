"""Confidence scoring for recruiter / professional contact affiliation.

Deterministic and explainable: a contact is only surfaced when its affiliation
with the target company is VERIFIED (public evidence on a company page or a
public directory entry) and scores >= 70. Guessed email addresses are never
accepted: the scorer only passes through an email that a public source
explicitly listed, which the discovery service stores (or discards).
"""

from dataclasses import dataclass, field

from backend.models.recruiter_contact import ContactType

RECRUITER_TITLE_KEYWORDS = (
    "recruiter",
    "talent acquisition",
    "talent",
    "people",
    "hiring",
    "sourcer",
    "head of hr",
    "hr",
    "hrbp",
    "talent partner",
)


@dataclass
class AffiliationConfidence:
    """Result of scoring one candidate contact against a target company."""

    score: int
    contact_type: ContactType
    surfaced: bool
    reasons: list[str] = field(default_factory=list)


def is_recruiting_role(role_title: str) -> bool:
    label = (role_title or "").strip().lower()
    return any(keyword in label for keyword in RECRUITER_TITLE_KEYWORDS)


class AffiliationConfidenceScorer:
    """Scores affiliation evidence; never guesses email addresses."""

    def score(
        self,
        *,
        role_title: str,
        on_company_domain: bool,
        has_public_profile_url: bool,
        email_publicly_listed: bool = False,
    ) -> AffiliationConfidence:
        reasons: list[str] = []
        score = 0

        if on_company_domain:
            score += 45
            reasons.append("public evidence on the company's own page")
        if is_recruiting_role(role_title):
            score += 20
            reasons.append("role title is plainly recruiting-related")
        if has_public_profile_url:
            score += 20
            reasons.append("linked public profile available as evidence")
        if role_title.strip() and on_company_domain and has_public_profile_url:
            score += 10
            reasons.append("name, role, and public evidence all present")
        if email_publicly_listed:
            # Bonus only: the public source explicitly exposed this address.
            score += 5
            reasons.append("email listed by the public source itself")

        score = max(0, min(100, score))
        verified = on_company_domain and is_recruiting_role(role_title)
        contact_type = ContactType.VERIFIED if verified else ContactType.GUESSED
        surfaced = score >= 70 and contact_type == ContactType.VERIFIED
        if not surfaced:
            reasons.append("affiliation not verified to the 70pt threshold")
        return AffiliationConfidence(
            score=score,
            contact_type=contact_type,
            surfaced=surfaced,
            reasons=reasons,
        )
