"""Auth service."""

from datetime import UTC, datetime
from uuid import UUID

from backend.core.exceptions import ValidationError
from backend.core.security_service import get_security_service
from backend.models.user import User
from backend.repositories.user import UserRepository
from backend.schemas.auth import UserLogin, UserRegister


class AuthService:
    def __init__(self, repo: UserRepository) -> None:
        self.repo = repo
        self.security = get_security_service()

    async def register(self, data: UserRegister) -> User:
        existing = await self.repo.get_by_email(data.email)
        if existing:
            raise ValidationError("An account with this email already exists")
        user = await self.repo.create_user(data.email, data.password)
        return user

    async def authenticate(self, data: UserLogin) -> User:
        user = await self.repo.get_by_email(data.email)
        if user is None or not self.security.verify_password(data.password, user.password_hash):
            raise ValidationError("Invalid email or password")
        if not user.is_active:
            raise ValidationError("Account is inactive")
        user.last_login_at = datetime.now(UTC)
        return user

    async def get_user(self, user_id: UUID) -> User | None:
        return await self.repo.get(user_id)
