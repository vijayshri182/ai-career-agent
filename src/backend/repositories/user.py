"""User repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security_service import get_security_service
from backend.models.user import User
from backend.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """User account repository."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)
        self.security = get_security_service()

    async def get_by_email(self, email: str) -> User | None:
        email_hash = self.security.hash_email(email)
        if email_hash is None:
            return None
        stmt = select(User).where(User.email_hash == email_hash)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_user(self, email: str, password: str) -> User:
        return await super().create(
            email_hash=self.security.hash_email(email),
            email_encrypted=self.security.encrypt(email),
            password_hash=self.security.hash_password(password),
        )
