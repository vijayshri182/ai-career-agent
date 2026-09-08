"""User authentication model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, String
from sqlmodel import Field, Relationship

from backend.db.base import IdModel

if TYPE_CHECKING:
    from backend.models.candidate import Candidate


class User(IdModel, table=True):
    """Authenticated user account."""

    __tablename__ = "users"

    email_hash: str = Field(sa_column=Column(String(64), unique=True, index=True, nullable=False))
    email_encrypted: str | None = Field(sa_column=Column(String(512), nullable=True))
    password_hash: str = Field(sa_column=Column(String(255), nullable=False))
    is_active: bool = Field(default=True)
    last_login_at: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    candidates: list["Candidate"] = Relationship(back_populates="user")

    @property
    def email(self) -> str | None:
        from backend.core.security_service import get_security_service

        return get_security_service().decrypt(self.email_encrypted)
