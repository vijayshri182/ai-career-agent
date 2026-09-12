"""add recruiter contact discovery foundation

Revision ID: d5e6f7a8b9c2
Revises: d4e5f6a7b8c1
Create Date: 2026-09-12

Phase 8 recruiter/professional contact discovery: ``contact_sources`` records
the public evidence page behind a discovery pass and ``recruiter_contacts`` one
candidate-scoped, company-scoped contact. Guessed emails are never stored; the
``email`` column only ever holds a publicly listed address. Only VERIFIED,
unsuppressed contacts with confidence >= 70 are surfaced by the API. Columns
mirror the lowercased-values convention used in recent phases.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c2"
down_revision: str | None = "d4e5f6a7b8c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contact_sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("source_type", sa.String(32), nullable=False, server_default="other_public"),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_contact_sources_candidate_id", "contact_sources", ["candidate_id"])
    op.create_index("ix_contact_sources_company_id", "contact_sources", ["company_id"])

    op.create_table(
        "recruiter_contacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("jobs.id"), nullable=True),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("contact_sources.id"), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role_title", sa.String(255), nullable=False),
        sa.Column("public_profile_url", sa.Text(), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("confidence_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("contact_type", sa.String(16), nullable=False, server_default="guessed"),
        sa.Column("is_suppressed", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("verification_details", sa.JSON(), nullable=True),
    )
    op.create_index("ix_recruiter_contacts_candidate_id", "recruiter_contacts", ["candidate_id"])
    op.create_index("ix_recruiter_contacts_company_id", "recruiter_contacts", ["company_id"])
    op.create_index("ix_recruiter_contacts_job_id", "recruiter_contacts", ["job_id"])
    op.create_index("ix_recruiter_contacts_source_id", "recruiter_contacts", ["source_id"])
    op.create_index(
        "uq_recruiter_contacts_candidate_profile",
        "recruiter_contacts",
        ["candidate_id", "public_profile_url"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("recruiter_contacts")
    op.drop_table("contact_sources")