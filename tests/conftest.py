"""Shared pytest fixtures."""

import os
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production-12345"
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode("utf-8")
os.environ["STORAGE_PROVIDER"] = "local"
os.environ["STORAGE_LOCAL_PATH"] = "./data/test_uploads"

from backend.app.main import app  # noqa: E402
from backend.core.config import get_settings  # noqa: E402
from backend.db.engine import make_session_factory  # noqa: E402
from backend.models import *  # noqa: F401, F403


@pytest_asyncio.fixture(scope="session")
async def engine():
    settings = get_settings()
    engine = create_async_engine(settings.database_url, future=True, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    async_session = make_session_factory(engine)
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
def override_dependencies(session):
    from backend.api.deps import get_session

    async def _get_session():
        yield session

    app.dependency_overrides[get_session] = _get_session
    yield
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(override_dependencies) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def test_user(session: AsyncSession):
    from backend.repositories.user import UserRepository

    repo = UserRepository(session)
    email = f"test-fixture-{uuid4().hex[:8]}@example.com"
    user = await repo.create_user(email, "StrongP@ssw0rd!")
    await session.commit()
    return user


@pytest.fixture
def auth_headers(test_user):
    from backend.core.security_service import get_security_service

    token = get_security_service().create_access_token({"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def candidate(test_user, session: AsyncSession):
    from backend.repositories.candidate import CandidateRepository

    repo = CandidateRepository(session)
    candidate = await repo.create_for_user(
        user_id=test_user.id,
        full_name="Test Candidate",
        email="candidate@example.com",
        headline="Senior Engineer",
        current_role="Engineering Lead",
        total_experience_years=12,
    )
    await session.commit()
    return candidate
