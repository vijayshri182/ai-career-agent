"""Add notifications and notification preferences foundation.

Revision ID: a1b2c3d4e5f6
Revises: f6a7b8c9d1e2
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f6a7b8c9d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> sa.Uuid:
    return sa.Uuid()


def _create_tables() -> None:
    op.create_table(
        "notifications",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("candidate_id", _uuid(), nullable=False, index=True),
        sa.Column(
            "category",
            sa.String(length=17),
            nullable=False,
            server_default="ERROR",
            index=True,
        ),
        sa.Column(
            "channel",
            sa.String(length=6),
            nullable=False,
            server_default="IN_APP",
            index=True,
        ),
        sa.Column(
            "status",
            sa.String(length=8),
            nullable=False,
            server_default="UNREAD",
            index=True,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.String(length=128), nullable=True),
        sa.Column("entity_id", sa.String(length=36), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"]),
    )
    op.create_table(
        "notification_preferences",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("candidate_id", _uuid(), nullable=False, unique=True, index=True),
        sa.Column("in_app_enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("sms_enabled", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("new_match_enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column(
            "approval_needed_enabled", sa.Boolean(), nullable=False, server_default="1"
        ),
        sa.Column(
            "application_update_enabled", sa.Boolean(), nullable=False, server_default="1"
        ),
        sa.Column(
            "outreach_response_enabled", sa.Boolean(), nullable=False, server_default="1"
        ),
        sa.Column("error_enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"]),
    )


def upgrade() -> None:
    _create_tables()


def downgrade() -> None:
    op.drop_table("notification_preferences")
    op.drop_table("notifications")