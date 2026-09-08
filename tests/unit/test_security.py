"""Security service tests."""

import pytest

from backend.core.config import Settings
from backend.core.security import SecurityService, generate_encryption_key


@pytest.fixture
def security():
    return SecurityService(
        Settings(app_env="test", encryption_key=generate_encryption_key())
    )


def test_encryption_round_trip(security: SecurityService):
    plain = "sensitive personal information"
    encrypted = security.encrypt(plain)
    assert encrypted != plain
    assert security.decrypt(encrypted) == plain


def test_email_hash_consistent(security: SecurityService):
    email = "Test@Example.COM"
    assert security.hash_email(email) == security.hash_email("test@example.com") == security.hash_email(" test@example.com ".strip())


def test_password_hashing(security: SecurityService):
    password = "StrongP@ssw0rd!"
    hashed = security.hash_password(password)
    assert security.verify_password(password, hashed)
    assert not security.verify_password("wrong", hashed)


def test_decrypt_invalid_value_fails(security: SecurityService):
    with pytest.raises(ValueError):
        security.decrypt("not-encrypted")
