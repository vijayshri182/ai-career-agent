"""add learning / optimization foundation

Revision ID: f6a7b8c9d1e2
Revises: e5f6a7b8c9d1
Create Date: 2026-09-12

Phase 12 learning: ``feedbacks`` capture observed post-submission outcomes
(offer / interview / rejection / ghosted / withdrawn) and ``recommendations``
hold fully explainable, purely suggestive guidance derived only from
candidate-owned data. Enum columns mirror SQLAlchemy's inferred ``Enum``
semantics from the models (uppercase member name stored); ``rationale`` is a
JSON list of the exact candidate-owned facts each recommendation cites.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d1e2"
down_revision: str | None = "e5f6a7b8c9d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feedbacks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey("applications.id"), nullable=True),
        sa.Column(
            "outreach_message_id",
            sa.Uuid(),
            sa.ForeignKey("outreach_messages.id"),
            nullable=True,
        ),
        sa.Column("outcome", sa.String(18), nullable=False, server_default="OTHER"),
        sa.Column("stage", sa.String(128), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("happened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_feedbacks_candidate_id", "feedbacks", ["candidate_id"])
    op.create_index("ix_feedbacks_application_id", "feedbacks", ["application_id"])
    op.create_index("ix_feedbacks_outreach_message_id", "feedbacks", ["outreach_message_id"])
    op.create_index("ix_feedbacks_outcome", "feedbacks", ["outcome"])

    op.create_table(
        "recommendations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("kind", sa.String(21), nullable=False),
        sa.Column("source_key", sa.String(255), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("rationale", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="ACTIVE"),
        sa.UniqueConstraint(
            "candidate_id", "kind", "source_key", name="uq_recommendations_candidate_kind_key"
        ),
    )
    op.create_index("ix_recommendations_candidate_id", "recommendations", ["candidate_id"])
    op.create_index("ix_recommendations_kind", "recommendations", ["kind"])
    op.create_index("ix_recommendations_status", "recommendations", ["status"])


def downgrade() -> None:
    op.drop_table("recommendations")
    op.drop_table("feedbacks")