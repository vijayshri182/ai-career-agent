"""Add ACA-owned Gate 4E ingestion and quarantine records.

Revision ID: c13b4e5f6a7d
Revises: a1b2c3d4e5f6
Create Date: 2026-09-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c13b4e5f6a7d"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gate4e_ingestion_records",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("candidate_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("producer_id", sa.String(length=128), nullable=False),
        sa.Column("producer_version", sa.String(length=32), nullable=False),
        sa.Column("ingestion_identity", sa.String(length=64), nullable=False),
        sa.Column(
            "processing_status",
            sa.String(length=32),
            nullable=False,
            server_default="REJECTED_INVALID",
            index=True,
        ),
        sa.Column("verification_status", sa.String(length=16), nullable=True),
        sa.Column("alert_index", sa.Integer(), nullable=True),
        sa.Column("gmail_message_id", sa.String(length=128), nullable=True),
        sa.Column("posting_key", sa.String(length=255), nullable=True, index=True),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("official_domain", sa.String(length=255), nullable=True),
        sa.Column("job_title", sa.String(length=512), nullable=True),
        sa.Column("job_location", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("official_job_url", sa.String(length=2048), nullable=True),
        sa.Column("official_job_id", sa.String(length=255), nullable=True),
        sa.Column("original_job_url", sa.String(length=2048), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True, index=True),
        sa.Column("job_id", sa.Uuid(), nullable=True, index=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("evidence_urls_json", sa.JSON(), nullable=False),
        sa.Column("enrichment_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.UniqueConstraint(
            "candidate_id",
            "ingestion_identity",
            name="uq_gate4e_ingestion_candidate_identity",
        ),
    )


def downgrade() -> None:
    op.drop_table("gate4e_ingestion_records")
