"""add application automation foundation

Revision ID: d4e5f6a7b8c1
Revises: c3a0912b7d01
Create Date: 2026-09-12

Phase 7 permitted application automation: an ``automation_runs`` record tracks
one candidate-scoped application submission workflow. It is gated by an
APPROVED approval and a source that explicitly permits automation, is paused
for human challenges, and retries within an attempt budget. Columns mirror the
SQLModel lowercased-values convention used by earlier phases.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c1"
down_revision: str | None = "c3a0912b7d01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "automation_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey("applications.id"), nullable=False),
        sa.Column("provider_id", sa.Uuid(), sa.ForeignKey("auth_providers.id"), nullable=True),
        sa.Column("challenge_id", sa.String(36), nullable=True),
        sa.Column("workflow_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("context_metadata", sa.JSON(), nullable=True),
        sa.Column("result_metadata", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_automation_runs_candidate_id", "automation_runs", ["candidate_id"])
    op.create_index("ix_automation_runs_application_id", "automation_runs", ["application_id"])
    op.create_index("ix_automation_runs_provider_id", "automation_runs", ["provider_id"])
    op.create_index("ix_automation_runs_challenge_id", "automation_runs", ["challenge_id"])
    op.create_index("ix_automation_runs_workflow_id", "automation_runs", ["workflow_id"])
    op.create_index("ix_automation_runs_status", "automation_runs", ["status"])
    op.create_index(
        "uq_automation_runs_open_app",
        "automation_runs",
        ["application_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('pending', 'running', 'paused_human_action')"),
        postgresql_where=sa.text("status IN ('pending', 'running', 'paused_human_action')"),
    )


def downgrade() -> None:
    op.drop_table("automation_runs")