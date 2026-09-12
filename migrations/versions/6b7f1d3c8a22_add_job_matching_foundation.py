"""add job matching foundation

Revision ID: 6b7f1d3c8a22
Revises: 5e5f4c256726
Create Date: 2026-09-11

Job match results produced by the explainable matching engine: one row per
(candidate, job), re-evaluated in place (idempotent) with provenance.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6b7f1d3c8a22"
down_revision: str | None = "5e5f4c256726"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_matches",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("is_match", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("matched_skills", sa.JSON(), nullable=False),
        sa.Column("missing_skills", sa.JSON(), nullable=False),
        sa.Column("transferable_skills", sa.JSON(), nullable=False),
        sa.Column("strengths", sa.JSON(), nullable=False),
        sa.Column("gaps", sa.JSON(), nullable=False),
        sa.Column("blockers", sa.JSON(), nullable=False),
        sa.Column("recommendation_reasons", sa.JSON(), nullable=False),
        sa.Column("rejection_reasons", sa.JSON(), nullable=False),
        sa.Column("score_breakdown", sa.JSON(), nullable=False),
        sa.Column("rules_version", sa.String(64), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "candidate_id", "job_id", name="uq_job_matches_candidate_job"
        ),
    )
    op.create_index("ix_job_matches_candidate_id", "job_matches", ["candidate_id"])
    op.create_index("ix_job_matches_job_id", "job_matches", ["job_id"])
    op.create_index("ix_job_matches_status", "job_matches", ["status"])
    op.create_index("ix_job_matches_is_match", "job_matches", ["is_match"])


def downgrade() -> None:
    op.drop_table("job_matches")