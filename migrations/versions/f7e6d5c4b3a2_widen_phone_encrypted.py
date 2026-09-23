"""widen candidates.phone_encrypted for Fernet ciphertext

Revision ID: f7e6d5c4b3a2
Revises: f6e5d4c3b2a1
Create Date: 2026-09-23

PostgreSQL defect fix: ``candidates.phone_encrypted`` was ``VARCHAR(64)`` but a
Fernet-encrypted phone number produces a ~100-120 character token, so persisting
an extracted phone during ``apply-parsed`` failed with
``asyncpg.StringDataRightTruncationError``. Widened to ``VARCHAR(512)`` to match
the sibling encrypted field ``email_encrypted`` with generous safety margin.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7e6d5c4b3a2"
down_revision: str | None = "f6e5d4c3b2a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "candidates",
        "phone_encrypted",
        existing_type=sa.String(length=64),
        type_=sa.String(length=512),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "candidates",
        "phone_encrypted",
        existing_type=sa.String(length=512),
        type_=sa.String(length=64),
        existing_nullable=True,
    )