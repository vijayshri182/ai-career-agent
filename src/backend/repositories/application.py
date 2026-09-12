"""Application preparation repositories."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models.application import (
    Application,
    ApplicationAnswer,
    ApplicationDocument,
    ApplicationQuestion,
    ApplicationStatus,
    DocumentType,
)
from backend.repositories.base import BaseRepository


class ApplicationRepository(BaseRepository[Application]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Application)

    async def list_for_candidate(
        self, candidate_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> list[Application]:
        stmt = (
            select(Application)
            .where(Application.candidate_id == candidate_id)
            .order_by(Application.__table__.c.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_candidate(self, application_id: UUID, candidate_id: UUID) -> Application | None:
        stmt = select(Application).where(
            Application.id == application_id,
            Application.candidate_id == candidate_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_job(self, job_id: UUID, candidate_id: UUID) -> Application | None:
        stmt = select(Application).where(
            Application.job_id == job_id,
            Application.candidate_id == candidate_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_detailed(self, application_id: UUID, candidate_id: UUID) -> Application | None:
        stmt = (
            select(Application)
            .where(
                Application.id == application_id,
                Application.candidate_id == candidate_id,
            )
            .options(
                selectinload(Application.questions).selectinload(ApplicationQuestion.answer),
                selectinload(Application.documents),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_for_candidate(self, candidate_id: UUID) -> int:
        stmt = (
            select(func.count()).select_from(Application).where(Application.candidate_id == candidate_id)
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_by_status(self, candidate_id: UUID) -> dict[ApplicationStatus, int]:
        stmt = (
            select(Application.status, func.count())
            .select_from(Application)
            .where(Application.candidate_id == candidate_id)
            .group_by(Application.status)
        )
        rows = (await self.session.execute(stmt)).all()
        return {ApplicationStatus(status): int(count) for status, count in rows}


class ApplicationQuestionRepository(BaseRepository[ApplicationQuestion]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ApplicationQuestion)

    async def list_for_application(self, application_id: UUID) -> list[ApplicationQuestion]:
        stmt = (
            select(ApplicationQuestion)
            .where(ApplicationQuestion.application_id == application_id)
            .order_by(ApplicationQuestion.__table__.c.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ApplicationAnswerRepository(BaseRepository[ApplicationAnswer]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ApplicationAnswer)

    async def list_for_application(self, application_id: UUID) -> list[ApplicationAnswer]:
        stmt = (
            select(ApplicationAnswer)
            .where(ApplicationAnswer.application_id == application_id)
            .order_by(ApplicationAnswer.__table__.c.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_question(self, question_id: UUID) -> ApplicationAnswer | None:
        stmt = select(ApplicationAnswer).where(ApplicationAnswer.question_id == question_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class ApplicationDocumentRepository(BaseRepository[ApplicationDocument]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ApplicationDocument)

    async def list_for_application(
        self, application_id: UUID, *, doc_type: DocumentType | None = None
    ) -> list[ApplicationDocument]:
        stmt = select(ApplicationDocument).where(
            ApplicationDocument.application_id == application_id
        )
        if doc_type is not None:
            stmt = stmt.where(ApplicationDocument.doc_type == doc_type)
        stmt = stmt.order_by(ApplicationDocument.__table__.c.version_number.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_application(
        self, document_id: UUID, application_id: UUID
    ) -> ApplicationDocument | None:
        stmt = select(ApplicationDocument).where(
            ApplicationDocument.id == document_id,
            ApplicationDocument.application_id == application_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def next_version_number(self, application_id: UUID, *, doc_type: DocumentType) -> int:
        stmt = (
            select(ApplicationDocument.version_number)
            .where(
                ApplicationDocument.application_id == application_id,
                ApplicationDocument.doc_type == doc_type,
            )
            .order_by(ApplicationDocument.__table__.c.version_number.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        latest = result.scalar_one_or_none()
        return (latest or 0) + 1
