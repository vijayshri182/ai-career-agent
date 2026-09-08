"""Security helpers for encryption, hashing, and JWT auth."""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import jwt
from cryptography.fernet import Fernet, InvalidToken
from passlib.context import CryptContext  # type: ignore[import-untyped]

from backend.core.config import Settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class SecurityService:
    """Handles encryption, password hashing, and email hashing."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._fernet = self._build_fernet()

    def _build_fernet(self) -> Fernet | None:
        if self.settings.encryption_key:
            return Fernet(self.settings.encryption_key)
        if self.settings.app_env == "test":
            # deterministic test key; never used for real data
            return Fernet(Fernet.generate_key())
        return None

    def encrypt(self, value: str | None) -> str | None:
        """Encrypt a string. Returns None if input is None."""
        if value is None:
            return None
        if self._fernet is None:
            raise RuntimeError("ENCRYPTION_KEY is not configured")
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, value: str | None) -> str | None:
        """Decrypt a string. Returns None if input is None."""
        if value is None:
            return None
        if self._fernet is None:
            raise RuntimeError("ENCRYPTION_KEY is not configured")
        try:
            return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Unable to decrypt value") from exc

    def hash_email(self, email: str | None) -> str | None:
        if email is None:
            return None
        return hashlib.sha256(email.lower().strip().encode("utf-8")).hexdigest()

    def verify_email(self, email: str, hashed: str | None) -> bool:
        return hashed is not None and self.hash_email(email) == hashed

    def hash_password(self, password: str) -> str:
        return cast(str, pwd_context.hash(password))

    def verify_password(self, password: str, hashed: str) -> bool:
        return cast(bool, pwd_context.verify(password, hashed))

    def create_access_token(self, data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
        to_encode = data.copy()
        expire = datetime.now(UTC) + (
            expires_delta or timedelta(minutes=self.settings.access_token_expire_minutes)
        )
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, self.settings.secret_key, algorithm="HS256")

    def decode_access_token(self, token: str) -> dict[str, Any]:
        return jwt.decode(token, self.settings.secret_key, algorithms=["HS256"])


def generate_encryption_key() -> str:
    """Generate a new URL-safe base64-encoded 32-byte Fernet key."""
    return Fernet.generate_key().decode("utf-8")
