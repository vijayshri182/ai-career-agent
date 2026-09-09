"""add applied_fields to parsed_resumes

Revision ID: c4f8a19b2d71
Revises: 87990926037c
Create Date: 2026-09-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4f8a19b2d71"
down_revision: Union[str, Sequence[str], None] = "87990926037c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add applied_fields column recording which candidate profile fields a parsed resume has already applied."""
    op.add_column(
        "parsed_resumes", sa.Column("applied_fields", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    """Remove applied_fields column."""
    op.drop_column("parsed_resumes", "applied_fields")