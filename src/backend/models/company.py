"""Employer (company) models for the promise of a normalized job universe."""

from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Column, Index, String, text
from sqlmodel import Field, Relationship

from backend.db.base import IdModel

if TYPE_CHECKING:
    from backend.models.job import Job


class CompanyVerificationStatus(str, Enum):
    """Trust level of a stored employer."""

    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    REJECTED = "rejected"


class Company(IdModel, table=True):
    """Normalized employer referenced by job postings.

    `website_domain` is unique only among verified companies: sources may report
    slightly different domains for the same employer; once a domain is verified
    it becomes the canonical key used to tie postings together.
    """

    __tablename__ = "companies"
    __table_args__ = (
        Index(
            "uq_companies_domain_verified",
            "website_domain",
            unique=True,
            sqlite_where=text("verification_status = 'VERIFIED'"),
            postgresql_where=text("verification_status = 'VERIFIED'"),
        ),
    )

    name: str = Field(sa_column=Column(String(255), nullable=False))
    website_domain: str | None = Field(sa_column=Column(String(255), index=True, nullable=True))
    careers_url: str | None = Field(sa_column=Column(String(1024), nullable=True))
    verification_status: CompanyVerificationStatus = Field(
        default=CompanyVerificationStatus.UNVERIFIED
    )

    jobs: list["Job"] = Relationship(back_populates="company")
