"""Resume service."""

import contextlib
import mimetypes
import os
from datetime import UTC, datetime
from uuid import UUID

from fastapi import UploadFile

from backend.core.config import Settings
from backend.core.exceptions import NotFoundError, ValidationError
from backend.models.resume import ParsedResume, Resume, ResumeStatus, ResumeType, ResumeVersion
from backend.repositories.audit import AuditRepository
from backend.repositories.resume import (
    ParsedResumeRepository,
    ResumeRepository,
    ResumeVersionRepository,
)
from backend.schemas.resume import ResumeCreate, ResumeUpdate
from backend.services.parser import BasicResumeParser, ResumeParser
from backend.services.storage import FileStorage

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}


class ResumeService:
    def __init__(
        self,
        resume_repo: ResumeRepository,
        version_repo: ResumeVersionRepository,
        parsed_repo: ParsedResumeRepository,
        audit_repo: AuditRepository,
        storage: FileStorage,
        parser: ResumeParser | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.resume_repo = resume_repo
        self.version_repo = version_repo
        self.parsed_repo = parsed_repo
        self.audit_repo = audit_repo
        self.storage = storage
        self.parser = parser or BasicResumeParser()
        self.settings = settings or __import__("backend.core.config", fromlist=["get_settings"]).get_settings()

    async def list_resumes(self, candidate_id: UUID) -> list[Resume]:
        return await self.resume_repo.list_active(candidate_id)

    async def get_resume(self, candidate_id: UUID, resume_id: UUID) -> Resume:
        resume = await self.resume_repo.get_with_active_version(resume_id)
        if resume is None or resume.candidate_id != candidate_id:
            raise NotFoundError("Resume not found")
        return resume

    async def create_resume(
        self, candidate_id: UUID, user_id: UUID, data: ResumeCreate
    ) -> Resume:
        resume = await self.resume_repo.create(
            candidate_id=candidate_id,
            name=data.name,
            resume_type=data.resume_type,
            target_role=data.target_role,
            is_default=data.is_default,
            status=ResumeStatus.ACTIVE,
        )
        await self.audit_repo.log(
            event_type="RESUME_CREATED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="Resume",
            entity_id=resume.id,
            metadata={"name": data.name},
        )
        return resume

    async def update_resume(
        self, candidate_id: UUID, user_id: UUID, resume_id: UUID, data: ResumeUpdate
    ) -> Resume:
        resume = await self.get_resume(candidate_id, resume_id)
        resume = await self.resume_repo.update(resume, **data.model_dump(exclude_unset=True))
        await self.audit_repo.log(
            event_type="RESUME_UPDATED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="Resume",
            entity_id=resume.id,
        )
        return resume

    async def delete_resume(self, candidate_id: UUID, user_id: UUID, resume_id: UUID) -> None:
        resume = await self.get_resume(candidate_id, resume_id)
        for version in resume.versions:
            if version.storage_path:
                with contextlib.suppress(FileNotFoundError):
                    await self.storage.delete(version.storage_path)
        resume = await self.resume_repo.update(resume, status=ResumeStatus.DELETED)
        await self.audit_repo.log(
            event_type="RESUME_DELETED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="Resume",
            entity_id=resume.id,
        )

    async def upload_resume(
        self,
        candidate_id: UUID,
        user_id: UUID,
        resume_id: UUID | None,
        file: UploadFile,
    ) -> ResumeVersion:
        content = await file.read()
        await self._validate_upload(content, file.filename, file.content_type)

        if resume_id:
            resume = await self.get_resume(candidate_id, resume_id)
        else:
            resume = await self.resume_repo.create(
                candidate_id=candidate_id,
                name=file.filename or "Uploaded Resume",
                resume_type=ResumeType.GENERAL,
                is_default=False,
                status=ResumeStatus.ACTIVE,
            )
            resume_id = resume.id

        version_number = await self.resume_repo.next_version_number(resume_id)
        version_id = UUID(os.urandom(16).hex(), version=4)

        content_type = file.content_type or (
            mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
        )
        safe_filename = os.path.basename(file.filename or "resume")
        storage_path = await self.storage.write(
            file_id=version_id,
            content=content,
            content_type=content_type,
            original_filename=safe_filename,
        )

        version = await self.version_repo.create(
            id=version_id,
            resume_id=resume_id,
            version_number=version_number,
            original_filename=safe_filename,
            storage_backend=self.settings.storage_provider,
            storage_path=storage_path,
            content_type=content_type,
            size_bytes=len(content),
            parsed_status="pending",
        )

        await self.resume_repo.update(resume, active_version_id=version.id)

        await self.audit_repo.log(
            event_type="RESUME_UPLOADED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="ResumeVersion",
            entity_id=version.id,
            metadata={
                "filename": safe_filename,
                "content_type": content_type,
                "size_bytes": len(content),
            },
        )
        return version

    async def _validate_upload(
        self, content: bytes, filename: str | None, content_type: str | None
    ) -> None:
        if len(content) > self.settings.max_upload_size_bytes:
            raise ValidationError("File exceeds maximum upload size")
        ext = os.path.splitext(filename or "")[1].lower().lstrip(".")
        if ext not in self.settings.allowed_resume_extensions:
            raise ValidationError(f"File extension '.{ext}' is not allowed")
        if content_type not in ALLOWED_MIME_TYPES:
            raise ValidationError(f"Content type '{content_type}' is not allowed")

    async def parse_resume(
        self, candidate_id: UUID, user_id: UUID, resume_id: UUID
    ) -> ParsedResume:
        resume = await self.get_resume(candidate_id, resume_id)
        active_version = await self.version_repo.get(resume.active_version_id) if resume.active_version_id else None
        if active_version is None:
            raise NotFoundError("Resume has no uploaded version")

        content = await self.storage.read(active_version.storage_path)
        parsed_data = await self.parser.parse(content, active_version.content_type)

        existing = await self.parsed_repo.get_by_version(active_version.id)
        if existing:
            parsed = await self.parsed_repo.update(
                existing,
                raw_text=parsed_data.raw_text,
                extracted_data=parsed_data.to_dict(),
                status="pending",
                confidence_score=None,
            )
        else:
            parsed = await self.parsed_repo.create(
                resume_version_id=active_version.id,
                raw_text=parsed_data.raw_text,
                extracted_data=parsed_data.to_dict(),
                status="pending",
            )

        active_version = await self.version_repo.update(
            active_version,
            parsed_status="parsed",
            parsed_at=datetime.now(UTC),
        )

        await self.audit_repo.log(
            event_type="RESUME_PARSED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="ParsedResume",
            entity_id=parsed.id,
            metadata={"resume_version_id": str(active_version.id)},
        )
        return parsed

    async def get_parsed_resume(
        self, candidate_id: UUID, resume_id: UUID
    ) -> ParsedResume:
        resume = await self.get_resume(candidate_id, resume_id)
        active_version = await self.version_repo.get(resume.active_version_id) if resume.active_version_id else None
        if active_version is None:
            raise NotFoundError("Resume has no uploaded version")
        parsed = await self.parsed_repo.get_by_version(active_version.id)
        if parsed is None:
            raise NotFoundError("Resume has not been parsed yet")
        return parsed

    async def apply_parsed_resume(
        self, candidate_id: UUID, user_id: UUID, resume_id: UUID
    ) -> ParsedResume:
        parsed = await self.get_parsed_resume(candidate_id, resume_id)
        parsed = await self.parsed_repo.update(
            parsed,
            status="applied",
            applied_at=datetime.now(UTC),
        )
        await self.audit_repo.log(
            event_type="RESUME_PARSED_APPLIED",
            actor_id=user_id,
            candidate_id=candidate_id,
            entity_type="ParsedResume",
            entity_id=parsed.id,
        )
        return parsed
