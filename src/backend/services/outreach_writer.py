"""Deterministic, fact-grounded outreach drafting.

Outreach may only be generated for a VERIFIED recruiter contact and must be
grounded exclusively in verified candidate facts plus verified contact/job
information. Nothing here invents experience, employers, titles, technologies,
certifications, achievements, metrics, relationships, referrals or previous
communication. Every sentence is assembled from the candidate profile, the
contact's verified role/name, and the verified job/company, and the whole draft
is re-validated by a grounding guard before it is persisted.

External recruiter/profile/job content remains untrusted: it never enters the
templates below and can never override the safety rules.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field

from backend.models.candidate import Candidate, Experience
from backend.models.outreach import OutreachChannel
from backend.models.recruiter_contact import RecruiterContact
from backend.services.application_prep import (
    FactGroundingValidator,
    FactSource,
    ProfileFacts,
    _FactKind,
)

OUTREACH_RULES_VERSION = "1.0.0"

SUBJECT_MAX = 150

_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+#./\-]{1,}")


@dataclass
class GeneratedOutreach:
    """A grounded, ready-for-review outreach draft."""

    subject: str
    body: str
    fact_sources: list[FactSource] = field(default_factory=list)


def _contact_facts(contact: RecruiterContact) -> list[FactSource]:
    facts: list[FactSource] = []
    if contact.full_name:
        facts.append(FactSource(_FactKind.CONTACT, contact.full_name, contact.id))
    if contact.role_title:
        facts.append(FactSource(_FactKind.CONTACT, contact.role_title, contact.id))
    return facts


def _contact_tokens(contact: RecruiterContact | None) -> set[str]:
    tokens: set[str] = set()
    if contact is None:
        return tokens
    for text in (contact.full_name, contact.role_title):
        if not text:
            continue
        tokens.add(text.lower())
        tokens.update(t.lower() for t in _TOKEN_RE.findall(text))
    return tokens


class ContactGroundedValidator(FactGroundingValidator):
    """Grounding guard that also permits the verified contact's identity.

    The contact's full name and role title are verified evidence (public
    source, confidence >= 70, unsuppressed) so they are added to the claim
    corpus for validation.
    """

    def __init__(
        self,
        skill_names: set[str] | None = None,
        *,
        contact: RecruiterContact | None = None,
    ) -> None:
        super().__init__(skill_names)
        self.contact = contact

    def validate(self, text: str, facts: ProfileFacts) -> list[str]:
        corpus = facts.claim_corpus() | _contact_tokens(self.contact)
        unsupported: list[str] = []
        for sentence in self._sentences(text):
            if self._unsupported(sentence, corpus):
                unsupported.append(sentence)
        return unsupported


class OutreachWriter(ABC):
    """Interface for outreach draft writers."""

    rules_version: str = OUTREACH_RULES_VERSION

    @abstractmethod
    async def generate(
        self,
        facts: ProfileFacts,
        contact: RecruiterContact,
        *,
        channel: OutreachChannel = OutreachChannel.EMAIL,
    ) -> GeneratedOutreach:
        """Produce a grounded initial outreach draft for a verified contact."""

    @abstractmethod
    async def generate_follow_up(
        self,
        facts: ProfileFacts,
        contact: RecruiterContact,
        *,
        parent_subject: str,
        channel: OutreachChannel = OutreachChannel.EMAIL,
    ) -> GeneratedOutreach:
        """Produce a grounded follow-up draft for a sent outreach message."""

    @abstractmethod
    async def validate(
        self,
        generated: GeneratedOutreach,
        facts: ProfileFacts,
        contact: RecruiterContact,
    ) -> list[str]:
        """Return unsupported claims found in a draft."""


class DeterministicOutreachWriter(OutreachWriter):
    """Templated deterministic writer grounded in profile + verified inputs."""

    def __init__(
        self,
        validator_factory: Callable[[RecruiterContact | None], ContactGroundedValidator] | None = None,
    ) -> None:
        # Delayed so each validation builds a fresh validator bound to a contact.
        self._validator_factory = validator_factory

    def _validator(self, contact: RecruiterContact | None) -> ContactGroundedValidator:
        if self._validator_factory is not None:
            return self._validator_factory(contact)
        return ContactGroundedValidator(contact=contact)

    async def generate(
        self,
        facts: ProfileFacts,
        contact: RecruiterContact,
        *,
        channel: OutreachChannel = OutreachChannel.EMAIL,
    ) -> GeneratedOutreach:
        subject = self._subject(facts, contact, follow_up=False)
        body = self._body(facts, contact, follow_up=False)
        return GeneratedOutreach(subject=subject, body=body, fact_sources=self._sources(facts, contact))

    async def generate_follow_up(
        self,
        facts: ProfileFacts,
        contact: RecruiterContact,
        *,
        parent_subject: str,
        channel: OutreachChannel = OutreachChannel.EMAIL,
    ) -> GeneratedOutreach:
        subject = self._subject(facts, contact, follow_up=True, parent_subject=parent_subject)
        body = self._body(facts, contact, follow_up=True)
        return GeneratedOutreach(subject=subject, body=body, fact_sources=self._sources(facts, contact))

    async def validate(
        self,
        generated: GeneratedOutreach,
        facts: ProfileFacts,
        contact: RecruiterContact,
    ) -> list[str]:
        validator = self._validator(contact)
        flagged = validator.validate(generated.subject, facts)
        flagged.extend(validator.validate(generated.body, facts))
        return flagged

    # -------------------------------------------------------------- assembly

    def _sources(self, facts: ProfileFacts, contact: RecruiterContact) -> list[FactSource]:
        sources = facts.entities() + _contact_facts(contact)
        job = facts.job
        company = facts.company
        if job is not None and job.title:
            sources.append(FactSource(_FactKind.JOB, job.title, job.id))
        if company is not None and company.name:
            sources.append(FactSource(_FactKind.JOB, company.name, company.id))
        return sources

    def _candidate(self, facts: ProfileFacts) -> Candidate | None:
        return facts.candidate

    def _lead(self, facts: ProfileFacts) -> str:
        candidate = facts.candidate
        for field_name in ("current_role", "headline", "target_role"):
            value = getattr(candidate, field_name, None) if candidate else None
            if value:
                return str(value)
        return "a professional"

    def _job_and_company(self, facts: ProfileFacts) -> tuple[str, str]:
        job_title = facts.job.title if facts.job is not None and facts.job.title else ""
        company = facts.company.name if facts.company is not None and facts.company.name else ""
        return job_title, company

    def _subject(
        self,
        facts: ProfileFacts,
        contact: RecruiterContact,
        *,
        follow_up: bool,
        parent_subject: str | None = None,
    ) -> str:
        if follow_up and parent_subject:
            subject = f"Re: {parent_subject}"
        else:
            job_title, company = self._job_and_company(facts)
            if job_title and company:
                subject = f"Application for {job_title} at {company}"
            elif company:
                subject = f"Introduction from {self._lead(facts)} for {company}"
            else:
                subject = f"Introduction from {self._lead(facts)}"
        return subject[:SUBJECT_MAX]

    def _body(self, facts: ProfileFacts, contact: RecruiterContact, *, follow_up: bool) -> str:
        candidate = facts.candidate
        job_title, company = self._job_and_company(facts)
        name = candidate.full_name if candidate and candidate.full_name else "the candidate"
        salutation = f"Dear {contact.full_name}," if contact.full_name else "Dear Recruiter,"
        grounded_skills = self._grounded_skill_names(facts)
        role_text = f" the {job_title} role" if job_title else " a role"
        company_text = f" at {company}" if company else ""
        current = self._current_experience(facts)

        if not follow_up:
            if current:
                skills_para = (
                    f"I bring relevant experience across {', '.join(grounded_skills)}."
                    if grounded_skills
                    else ""
                )
                career = (
                    f"I am currently {current.title} at {current.company_name}, and I am writing "
                    f"about{role_text}{company_text}."
                )
            else:
                skills_para = (
                    f"I bring relevant experience across {', '.join(grounded_skills)}."
                    if grounded_skills
                    else ""
                )
                career = (
                    f"I am {self._lead(facts)} and I am writing about{role_text}{company_text}."
                )
            body = "\n\n".join(part for part in (salutation, career, skills_para) if part)
            body += _CANDIDATE_LINK
        else:
            career = (
                f"I am following up on my application for{role_text}{company_text}. "
                f"I understand you may be busy, but I remain very interested in the opportunity"
                + (f" to contribute my experience in {', '.join(grounded_skills)}." if grounded_skills else ".")
            )
            body = "\n\n".join(part for part in (salutation, career) if part)
            body += _CANDIDATE_LINK

        body += f"\n\nSincerely,\n{name}"
        return body.strip()

    def _current_experience(self, facts: ProfileFacts) -> Experience | None:
        for exp in facts.experiences:
            if exp.is_current:
                return exp
        return None

    def _grounded_skill_names(self, facts: ProfileFacts) -> list[str]:
        """Profile-grounded skills (never raw untrusted job text)."""
        profile_names = {s.name.lower() for s in facts.skills}
        names = [s.name for s in facts.skills if s.name.lower() in profile_names]
        return sorted(names, key=str.lower)[:8]


_CANDIDATE_LINK = (
    "\n\nI would welcome the opportunity to discuss how my experience could "
    "contribute to the role. Thank you for your consideration."
)
