"""Encrypted SQLAlchemy column types used to protect PII."""

from typing import Any

from sqlalchemy import String, TypeDecorator
from sqlalchemy.engine.interfaces import Dialect

from backend.core.security_service import get_security_service


class EncryptedString(TypeDecorator[str]):
    """Transparently encrypt/decrypt a string column at the application layer."""

    impl = String
    cache_ok = True

    def __init__(self, length: int = 2048, **kwargs: Any) -> None:
        super().__init__(length=length, **kwargs)

    def process_bind_param(self, value: str | None, dialect: Dialect) -> str | None:  # noqa: ARG002
        if value is None:
            return None
        return get_security_service().encrypt(value)

    def process_result_value(self, value: str | None, dialect: Dialect) -> str | None:  # noqa: ARG002
        if value is None:
            return None
        return get_security_service().decrypt(value)
