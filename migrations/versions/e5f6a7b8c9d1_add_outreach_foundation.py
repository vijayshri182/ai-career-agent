"""add outreach engine foundation

Revision ID: e5f6a7b8c9d1
Revises: d5e6f7a8b9c2
Create Date: 2026-09-12

Phase 9 outreach: ``outreach_messages`` (one candidate-scoped message to a
VERIFIED recruiter contact), ``outreach_message_versions`` (append-only content
snapshots so edits/send history stay auditable) and ``outreach_runs`` (durable
send-attempt workflows; the partial unique index guarantees at most one
non-terminal run per message so a message can never be sent twice). Enum columns
mirror SQLAlchemy's inferred ``Enum`` semantics from the models (stored as the
uppercase member name, e.g. ``DRAFT``), matching prior phases. ``parent_id`` and
``approval_id`` are soft references; no secrets are stored here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d1"
down_revision: str | None = "d5e6f7a8b9c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outreach_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("contact_id", sa.Uuid(), sa.ForeignKey("recruiter_contacts.id"), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("jobs.id"), nullable=True),
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey("applications.id"), nullable=True),
        sa.Column("channel", sa.String(20), nullable=False, server_default="EMAIL"),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(17), nullable=False, server_default="DRAFT"),
        sa.Column("response_status", sa.String(11), nullable=False, server_default="NO_RESPONSE"),
        sa.Column("is_follow_up", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("parent_id", sa.Uuid(), sa.ForeignKey("outreach_messages.id"), nullable=True),
        sa.Column("approval_id", sa.String(36), nullable=True),
        sa.Column("rules_version", sa.String(32), nullable=True),
        sa.Column("fact_sources", sa.JSON(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_message_id", sa.String(255), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
    )
    op.create_index("ix_outreach_messages_candidate_id", "outreach_messages", ["candidate_id"])
    op.create_index("ix_outreach_messages_contact_id", "outreach_messages", ["contact_id"])
    op.create_index("ix_outreach_messages_job_id", "outreach_messages", ["job_id"])
    op.create_index("ix_outreach_messages_application_id", "outreach_messages", ["application_id"])
    op.create_index("ix_outreach_messages_channel", "outreach_messages", ["channel"])
    op.create_index("ix_outreach_messages_status", "outreach_messages", ["status"])
    op.create_index("ix_outreach_messages_response_status", "outreach_messages", ["response_status"])
    op.create_index("ix_outreach_messages_approval_id", "outreach_messages", ["approval_id"])
    op.create_index("ix_outreach_messages_parent", "outreach_messages", ["parent_id"])

    op.create_table(
        "outreach_message_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("message_id", sa.Uuid(), sa.ForeignKey("outreach_messages.id"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_generated", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("fact_sources", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
    )
    op.create_index("ix_outreach_message_versions_message_id", "outreach_message_versions", ["message_id"])
    op.create_index(
        "uq_outreach_message_versions_number",
        "outreach_message_versions",
        ["message_id", "version_number"],
        unique=True,
    )

    op.create_table(
        "outreach_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("message_id", sa.Uuid(), sa.ForeignKey("outreach_messages.id"), nullable=False),
        sa.Column("status", sa.String(9), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("result_metadata", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_message_id", sa.String(255), nullable=True),
    )
    op.create_index("ix_outreach_runs_candidate_id", "outreach_runs", ["candidate_id"])
    op.create_index("ix_outreach_runs_message_id", "outreach_runs", ["message_id"])
    op.create_index(
        "uq_outreach_runs_open_message",
        "outreach_runs",
        ["message_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('PENDING', 'RUNNING')"),
        postgresql_where=sa.text("status IN ('PENDING', 'RUNNING')"),
    )


def downgrade() -> None:
    op.drop_table("outreach_runs")
    op.drop_table("outreach_message_versions")
    op.drop_table("outreach_messages")