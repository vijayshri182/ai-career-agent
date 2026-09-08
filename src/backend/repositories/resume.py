"""Resume repository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models.resume import ParsedResume, Resume, ResumeStatus, ResumeVersion
from backend.repositories.base import BaseRepository


class ResumeRepository(BaseRepository[Resume]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Resume)

    async def list_active(self, candidate_id: UUID) -> list[Resume]:
        stmt = select(Resume).where(
            Resume.candidate_id == candidate_id, Resume.status != ResumeStatus.DELETED
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_with_active_version(self, resume_id: UUID) -> Resume | None:
        stmt = (
            select(Resume)
            .where(Resume.id == resume_id)
            .options(selectinload(Resume.versions))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def next_version_number(self, resume_id: UUID) -> int:
        stmt = (
            select(ResumeVersion.version_number)
            .where(ResumeVersion.resume_id == resume_id)
            .order_by(ResumeVersion.__table__.c.version_number.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        latest = result.scalar_one_or_none()
        return (latest or 0) + 1


class ResumeVersionRepository(BaseRepository[ResumeVersion]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ResumeVersion)


class ParsedResumeRepository(BaseRepository[ParsedResume]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ParsedResume)

    async def get_by_version(self, version_id: UUID) -> ParsedResume | None:
        stmt = select(ParsedResume).where(ParsedResume.resume_version_id == version_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
