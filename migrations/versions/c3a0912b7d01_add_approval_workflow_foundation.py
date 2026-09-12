"""add approval workflow foundation

Revision ID: c3a0912b7d01
Revises: b2fe40980eea
Create Date: 2026-09-12

Phase 6 human-in-the-loop approval workflow: an ``approvals`` record gates an
external action (application submission, outreach send) behind an explicit
human decision; every decision is appended to ``approval_decisions`` and
mirrored to the generic audit log. Enum-like columns store lowercase string
values matching the SQLModel lowercased-values convention.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3a0912b7d01"
down_revision: str | None = "b2fe40980eea"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "approvals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False, server_default="application_submission"),
        sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("target_type", sa.String(30), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey("applications.id"), nullable=True),
        sa.Column("autonomy_level", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("decided_by", sa.String(36), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_type", sa.String(12), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_approvals_candidate_id", "approvals", ["candidate_id"])
    op.create_index("ix_approvals_target_id", "approvals", ["target_id"])
    op.create_index("ix_approvals_status", "approvals", ["status"])
    op.create_index("ix_approvals_kind", "approvals", ["kind"])

    op.create_table(
        "approval_decisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("approval_id", sa.Uuid(), sa.ForeignKey("approvals.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("decision_type", sa.String(12), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_approval_decisions_approval_id", "approval_decisions", ["approval_id"])
    op.create_index("ix_approval_decisions_actor_id", "approval_decisions", ["actor_id"])


def downgrade() -> None:
    op.drop_table("approval_decisions")
    op.drop_table("approvals")