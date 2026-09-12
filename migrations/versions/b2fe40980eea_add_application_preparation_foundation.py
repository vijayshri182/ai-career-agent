"""add application preparation foundation

Revision ID: <gen>
Revises: 6b7f1d3c8a22
Create Date: 2026-09-12

Application preparation entities: one application per (candidate, job) that
tracks selected resume, screening questions, fact-grounded answers, and
versioned generated documents (cover letter, tailored resume, answer sheet).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2fe40980eea"
down_revision: str | None = "6b7f1d3c8a22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("resume_id", sa.Uuid(), sa.ForeignKey("resumes.id"), nullable=True),
        sa.Column("status", sa.String(9), nullable=False, server_default="draft"),
        sa.Column("match_id", sa.Uuid(), sa.ForeignKey("job_matches.id"), nullable=True),
        sa.Column("match_score", sa.Float(), nullable=True),
    )
    op.create_index("ix_applications_candidate_id", "applications", ["candidate_id"])
    op.create_index("ix_applications_job_id", "applications", ["job_id"])
    op.create_index("ix_applications_status", "applications", ["status"])

    op.create_table(
        "application_questions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey("applications.id"), nullable=False),
        sa.Column("category", sa.String(18), nullable=False, server_default="other"),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("source_hint", sa.String(128), nullable=True),
    )
    op.create_index(
        "ix_application_questions_application_id",
        "application_questions",
        ["application_id"],
    )

    op.create_table(
        "application_answers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey("applications.id"), nullable=False),
        sa.Column("question_id", sa.Uuid(), sa.ForeignKey("application_questions.id"), nullable=False),
        sa.Column("status", sa.String(15), nullable=False, server_default="requires_review"),
        sa.Column("answer_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("fact_sources", sa.JSON(), nullable=True),
        sa.UniqueConstraint("question_id", name="uq_application_answers_question"),
    )
    op.create_index(
        "ix_application_answers_application_id", "application_answers", ["application_id"]
    )

    op.create_table(
        "application_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey("applications.id"), nullable=False),
        sa.Column("doc_type", sa.String(15), nullable=False, server_default="other"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_generated", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("content", sa.String(65535), nullable=False, server_default=""),
        sa.Column("generation_version", sa.String(64), nullable=True),
        sa.Column("fact_sources", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_application_documents_application_id",
        "application_documents",
        ["application_id"],
    )


def downgrade() -> None:
    op.drop_table("application_documents")
    op.drop_table("application_answers")
    op.drop_table("application_questions")
    op.drop_table("applications")