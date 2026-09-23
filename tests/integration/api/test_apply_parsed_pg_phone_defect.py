"""PostgreSQL regression for encrypted phone persistence in apply-parsed.

The released schema declared ``candidates.phone_encrypted`` as ``VARCHAR(64)``
while the app's Fernet ciphertext is ~100-120 characters, so on PostgreSQL any
``apply-parsed`` carrying a phone number failed with
``asyncpg.StringDataRightTruncationError``. SQLite does not enforce VARCHAR
lengths, so the standard suite could not catch this defect.

The full apply-parsed scenario below is PostgreSQL-specific and is skipped
unless ``TEST_POSTGRESQL_URL`` points at a disposable PostgreSQL database. The
model invariant and the plain-text roundtrip tests always run so the default
suite still guards the column declaration and the read path. The read-path
defect this guards: the model ``phone`` property decrypts the column again
even though ``EncryptedString`` already applied its result transform, so phone
is stored with an outer ciphertext layer (mirroring email) to keep layers
balanced; single-layer storage makes every read raise
``ValueError: Unable to decrypt value``.
"""

import os
from io import BytesIO
from uuid import uuid4

import pytest
import pytest_asyncio
from docx import Document
from fastapi import UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

from backend.core.config import get_settings
from backend.db.engine import make_session_factory
from backend.models import *  # noqa: F401, F403
from backend.models.candidate import Candidate
from backend.models.resume import ResumeType
from backend.repositories.audit import AuditRepository
from backend.repositories.candidate import CandidateRepository
from backend.repositories.resume import (
    ParsedResumeRepository,
    ResumeRepository,
    ResumeVersionRepository,
)
from backend.repositories.skill import SkillRepository
from backend.repositories.user import UserRepository
from backend.schemas.resume import ResumeCreate
from backend.services.parser import BasicResumeParser
from backend.services.resume import ResumeService
from backend.services.storage import LocalFileStorage

TEST_URL = os.environ.get("TEST_POSTGRESQL_URL", "")
_SKIP_REASON = "TEST_POSTGRESQL_URL unset; PostgreSQL regression test skipped"


def _docx_bytes(text: str) -> tuple[bytes, str]:
    doc = Document()
    doc.add_paragraph(text)
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_model_phone_encrypted_column_has_capacity() -> None:
    """Model invariant: phone ciphertext column must fit a Fernet token."""
    column = Candidate.__table__.c.phone_encrypted
    assert column.type.length is not None
    assert column.type.length >= 256


@pytest.mark.asyncio
async def test_phone_roundtrip_with_fresh_read(session, engine) -> None:
    """Phone stored with the email-style outer layer reads back as plaintext."""
    user = await UserRepository(session).create_user(
        f"roundtrip-{uuid4().hex[:8]}@example.com", "StrongP@ssw0rd!9"
    )
    candidate = await CandidateRepository(session).create_for_user(
        user.id,
        email=f"rt-{uuid4().hex[:8]}@example.com",
        phone="+91 9148975538",
    )
    await session.commit()

    factory = make_session_factory(engine)
    async with factory() as fresh:
        reloaded = await fresh.get(Candidate, candidate.id)
        assert reloaded is not None
        assert reloaded.phone == "+91 9148975538"


async def _make_service(pg_session) -> ResumeService:
    settings = get_settings()
    return ResumeService(
        ResumeRepository(pg_session),
        ResumeVersionRepository(pg_session),
        ParsedResumeRepository(pg_session),
        AuditRepository(pg_session),
        CandidateRepository(pg_session),
        SkillRepository(pg_session),
        storage=LocalFileStorage(settings),
        parser=BasicResumeParser(),
        settings=settings,
    )


@pytest_asyncio.fixture
async def pg_session():
    engine = create_async_engine(TEST_URL, future=True)
    async with engine.begin() as conn:
        if TEST_URL.startswith("postgresql"):
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        else:
            await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    session_factory = make_session_factory(engine)
    async with session_factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest.mark.skipif(not TEST_URL, reason=_SKIP_REASON)
@pytest.mark.asyncio
async def test_apply_parsed_persists_phone_on_postgresql(pg_session) -> None:
    """Full upload -> parse -> apply cycle must persist phone without truncation."""
    user = await UserRepository(pg_session).create_user(
        f"pg-phone-{uuid4().hex[:8]}@example.com", "StrongP@ssw0rd!9"
    )
    email = f"pgc-{uuid4().hex[:8]}@example.com"
    candidate = await CandidateRepository(pg_session).create_for_user(
        user.id, email=email, full_name="PG Phone Test"
    )
    assert candidate.phone is None
    await pg_session.commit()

    service = await _make_service(pg_session)
    resume = await service.create_resume(
        candidate.id,
        user.id,
        ResumeCreate(name="PG Resume", resume_type=ResumeType.GENERAL),
    )

    content, ctype = _docx_bytes(
        "PG Phone Test\n"
        "pg.phone@example.com\n"
        "+91 9148975538\n"
        "Java PostgreSQL Kubernetes\n"
    )
    await service.upload_resume(
        candidate.id,
        user.id,
        resume.id,
        UploadFile(
            file=BytesIO(content),
            filename="pg_resume.docx",
            headers={"content-type": ctype},
        ),
    )

    parsed = await service.parse_resume(candidate.id, user.id, resume.id)
    assert parsed.extracted_data["phone"] == "+91 9148975538"

    applied = await service.apply_parsed_resume(candidate.id, user.id, resume.id)
    assert applied.status == "applied"
    assert "phone" in applied.applied_fields
    await pg_session.commit()

    pg = create_async_engine(TEST_URL, future=True)
    try:
        async with make_session_factory(pg)() as fresh_session:
            reloaded = await fresh_session.get(Candidate, candidate.id)
            assert reloaded is not None
            assert reloaded.phone == "+91 9148975538"
        async with pg.connect() as conn:
            row = await conn.execute(
                text(
                    "select character_maximum_length from information_schema.columns "
                    "where table_name='candidates' and column_name='phone_encrypted'"
                )
            )
            length = row.scalar()
            assert length is not None and length >= 256
    finally:
        await pg.dispose()
