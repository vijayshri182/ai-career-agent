"""Base mixin classes for SQLModel tables."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import DateTime, func
from sqlmodel import Field, SQLModel


class TimestampMixin(SQLModel):
    """Adds created_at and updated_at columns."""

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now(), "nullable": False},  # type: ignore[call-overload]
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={  # type: ignore[call-overload]
            "server_default": func.now(),
            "onupdate": func.now(),
            "nullable": False,
        },
    )


class IdModel(TimestampMixin):
    """Base table model with UUID primary key and timestamps."""

    id: UUID = Field(default_factory=lambda: __import__("uuid").uuid4(), primary_key=True)
