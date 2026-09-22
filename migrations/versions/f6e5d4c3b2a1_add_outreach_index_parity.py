"""restore outreach index parity with models

Revision ID: f6e5d4c3b2a1
Revises: d16a7c9e52b0
Create Date: 2026-09-22

Performance/parity fix: ``outreach_messages.parent_id`` was indexed by the
original migration under ``ix_outreach_messages_parent`` but the model declares
``index=True`` (canonical name ``ix_outreach_messages_parent_id``), and
``outreach_runs.status`` was never indexed even though the model declares
``index=True``. Aligns the real schema with the declared model metadata.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6e5d4c3b2a1"
down_revision: str | None = "d16a7c9e52b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_outreach_messages_parent", table_name="outreach_messages")
    op.create_index(
        "ix_outreach_messages_parent_id", "outreach_messages", ["parent_id"]
    )
    op.create_index("ix_outreach_runs_status", "outreach_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_outreach_runs_status", table_name="outreach_runs")
    op.drop_index("ix_outreach_messages_parent_id", table_name="outreach_messages")
    op.create_index(
        "ix_outreach_messages_parent", "outreach_messages", ["parent_id"]
    )