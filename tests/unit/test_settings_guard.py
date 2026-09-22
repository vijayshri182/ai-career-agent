"""Tests for production secret guard in settings."""

import pytest
from pydantic import ValidationError

from backend.core.config import Settings, get_settings


def test_production_rejects_placeholder_secret() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(_env_file=None, app_env="production", secret_key="change-me-in-production")


def test_production_rejects_empty_secret() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(_env_file=None, app_env="production", secret_key="")


def test_production_accepts_explicit_secret() -> None:
    settings = Settings(_env_file=None, app_env="production", secret_key="real-secret")
    assert settings.secret_key == "real-secret"


def test_dev_placeholder_secret_allowed() -> None:
    settings = Settings(_env_file=None, app_env="development", secret_key="change-me-in-production")
    assert settings.app_env == "development"


def test_get_settings_uses_cached_instance() -> None:
    get_settings.cache_clear()
    a = get_settings()
    b = get_settings()
    assert a is b
