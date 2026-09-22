"""Add recruiter signal domain model foundation.

Revision ID: d16a7c9e52b0
Revises: c13b4e5f6a7d
Create Date: 2026-09-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d16a7c9e52b0"
down_revision: str | None = "c13b4e5f6a7d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recruiter_signals",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("candidate_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("job_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("recruiter_contact_id", sa.Uuid(), nullable=True, index=True),
        sa.Column("company_id", sa.Uuid(), nullable=True, index=True),
        sa.Column(
            "signal_type",
            sa.String(length=40),
            nullable=False,
            server_default="recruiter_associated",
            index=True,
        ),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default="discovered",
            index=True,
        ),
        sa.Column("signal_identity", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["recruiter_contact_id"], ["recruiter_contacts.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.UniqueConstraint(
            "candidate_id",
            "signal_identity",
            name="uq_recruiter_signals_candidate_identity",
        ),
    )


def downgrade() -> None:
    op.drop_table("recruiter_signals")