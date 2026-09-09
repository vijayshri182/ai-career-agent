"""Service-layer ownership enforcement.

Services that accept a candidate_id must reject operations on candidates that
do not belong to the calling user, even when invoked directly (outside the
HTTP dependency layer). Cross-user and non-existent candidates are
indistinguishable and both raise NotFoundError; no data is created, read,
updated, or deleted in the process.
"""

from datetime import date
from io import BytesIO
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import (
    get_certification_service,
    get_education_service,
    get_experience_service,
    get_resume_service,
    get_skill_service,
)
from backend.core.exceptions import NotFoundError
from backend.models.resume import ResumeStatus, ResumeType
from backend.schemas.education import EducationCreate, EducationUpdate
from backend.schemas.experience import ExperienceCreate, ExperienceUpdate
from backend.schemas.resume import ResumeCreate, ResumeUpdate
from backend.schemas.skill import SkillCreate, SkillUpdate
from backend.services.certification import CertificationService
from backend.services.education import EducationService
from backend.services.experience import ExperienceService
from backend.services.resume import ResumeService
from backend.services.skill import SkillService

pytestmark = pytest.mark.asyncio

DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


@pytest_asyncio.fixture
async def foreign_candidate(session: AsyncSession):
    """A candidate owned by a different user, with one of every sub-resource."""
    from backend.repositories.candidate import CandidateRepository
    from backend.repositories.certification import CertificationRepository
    from backend.repositories.education import EducationRepository
    from backend.repositories.experience import ExperienceRepository
    from backend.repositories.resume import ResumeRepository
    from backend.repositories.skill import SkillRepository
    from backend.repositories.user import UserRepository

    user = await UserRepository(session).create_user(
        f"foreign-{uuid4().hex[:8]}@example.com", "ForeignPass123!"
    )
    candidate = await CandidateRepository(session).create_for_user(
        user_id=user.id, full_name="Foreign Candidate", email="foreign@example.com"
    )
    skill = await SkillRepository(session).create(candidate_id=candidate.id, name="Java")
    experience = await ExperienceRepository(session).create(
        candidate_id=candidate.id,
        company_name="Corp",
        title="Engineer",
        start_date=date(2020, 1, 1),
    )
    education = await EducationRepository(session).create(
        candidate_id=candidate.id, institution="Uni", degree="B.Sc"
    )
    certification = await CertificationRepository(session).create(
        candidate_id=candidate.id, name="AWS Certified"
    )
    resume = await ResumeRepository(session).create(
        candidate_id=candidate.id,
        name="Foreign Resume",
        resume_type=ResumeType.GENERAL,
        status=ResumeStatus.ACTIVE,
    )
    await session.commit()
    return {
        "candidate": candidate,
        "skill": skill,
        "experience": experience,
        "education": education,
        "certification": certification,
        "resume": resume,
    }


def _upload_file() -> UploadFile:
    return UploadFile(
        filename="resume.docx",
        file=BytesIO(b"content"),
        headers={"content-type": DOCX_CONTENT_TYPE},
    )


async def test_skill_service_rejects_foreign_candidate(
    session: AsyncSession, candidate, foreign_candidate
):
    from backend.repositories.skill import SkillRepository

    service: SkillService = await get_skill_service(session)
    fc = foreign_candidate["candidate"]
    fs = foreign_candidate["skill"]
    owner = candidate.user_id

    with pytest.raises(NotFoundError):
        await service.list(fc.id, owner)
    with pytest.raises(NotFoundError):
        await service.get(fc.id, owner, fs.id)
    with pytest.raises(NotFoundError):
        await service.add(fc.id, owner, SkillCreate(name="Python"))
    with pytest.raises(NotFoundError):
        await service.update(fc.id, owner, fs.id, SkillUpdate(proficiency="expert"))
    with pytest.raises(NotFoundError):
        await service.delete(fc.id, owner, fs.id)

    remaining = await SkillRepository(session).list(candidate_id=fs.candidate_id)
    assert [s.id for s in remaining] == [fs.id]


async def test_experience_service_rejects_foreign_candidate(
    session: AsyncSession, candidate, foreign_candidate
):
    service: ExperienceService = await get_experience_service(session)
    fc = foreign_candidate["candidate"]
    fe = foreign_candidate["experience"]
    owner = candidate.user_id

    with pytest.raises(NotFoundError):
        await service.list(fc.id, owner)
    with pytest.raises(NotFoundError):
        await service.get(fc.id, owner, fe.id)
    with pytest.raises(NotFoundError):
        await service.add(
            fc.id, owner, ExperienceCreate(company_name="C", title="T", start_date=date(2021, 1, 1))
        )
    with pytest.raises(NotFoundError):
        await service.update(fc.id, owner, fe.id, ExperienceUpdate(title="New"))
    with pytest.raises(NotFoundError):
        await service.delete(fc.id, owner, fe.id)


async def test_education_service_rejects_foreign_candidate(
    session: AsyncSession, candidate, foreign_candidate
):
    service: EducationService = await get_education_service(session)
    fc = foreign_candidate["candidate"]
    fed = foreign_candidate["education"]
    owner = candidate.user_id

    with pytest.raises(NotFoundError):
        await service.list(fc.id, owner)
    with pytest.raises(NotFoundError):
        await service.get(fc.id, owner, fed.id)
    with pytest.raises(NotFoundError):
        await service.add(fc.id, owner, EducationCreate(institution="U", degree="M.Sc"))
    with pytest.raises(NotFoundError):
        await service.update(fc.id, owner, fed.id, EducationUpdate(degree="PhD"))
    with pytest.raises(NotFoundError):
        await service.delete(fc.id, owner, fed.id)


async def test_certification_service_rejects_foreign_candidate(
    session: AsyncSession, candidate, foreign_candidate
):
    from backend.schemas.certification import CertificationCreate, CertificationUpdate

    service: CertificationService = await get_certification_service(session)
    fc = foreign_candidate["candidate"]
    fcert = foreign_candidate["certification"]
    owner = candidate.user_id

    with pytest.raises(NotFoundError):
        await service.list(fc.id, owner)
    with pytest.raises(NotFoundError):
        await service.get(fc.id, owner, fcert.id)
    with pytest.raises(NotFoundError):
        await service.add(fc.id, owner, CertificationCreate(name="GCP"))
    with pytest.raises(NotFoundError):
        await service.update(fc.id, owner, fcert.id, CertificationUpdate(name="Renamed"))
    with pytest.raises(NotFoundError):
        await service.delete(fc.id, owner, fcert.id)


async def test_resume_service_rejects_foreign_candidate(
    session: AsyncSession, candidate, foreign_candidate
):
    service: ResumeService = await get_resume_service(session)
    fc = foreign_candidate["candidate"]
    fr = foreign_candidate["resume"]
    owner = candidate.user_id

    with pytest.raises(NotFoundError):
        await service.list_resumes(fc.id, owner)
    with pytest.raises(NotFoundError):
        await service.create_resume(fc.id, owner, ResumeCreate(name="X"))
    with pytest.raises(NotFoundError):
        await service.get_resume(fc.id, owner, fr.id)
    with pytest.raises(NotFoundError):
        await service.update_resume(fc.id, owner, fr.id, ResumeUpdate(name="Y"))
    with pytest.raises(NotFoundError):
        await service.delete_resume(fc.id, owner, fr.id)
    with pytest.raises(NotFoundError):
        await service.upload_resume(fc.id, owner, fr.id, _upload_file())
    with pytest.raises(NotFoundError):
        await service.upload_resume(fc.id, owner, None, _upload_file())
    with pytest.raises(NotFoundError):
        await service.parse_resume(fc.id, owner, fr.id)
    with pytest.raises(NotFoundError):
        await service.get_parsed_resume(fc.id, owner, fr.id)
    with pytest.raises(NotFoundError):
        await service.apply_parsed_resume(fc.id, owner, fr.id)


async def test_services_reject_nonexistent_candidate(
    session: AsyncSession, candidate
):
    service = await get_experience_service(session)
    with pytest.raises(NotFoundError):
        await service.list(uuid4(), candidate.user_id)


async def test_owner_can_use_services(
    session: AsyncSession, candidate, foreign_candidate
):
    service: SkillService = await get_skill_service(session)
    assert await service.list(candidate.id, candidate.user_id) == []

    added = await service.add(candidate.id, candidate.user_id, SkillCreate(name="Go"))
    assert added.candidate_id == candidate.id


async def test_cross_user_update_does_not_touch_foreign_data(
    session: AsyncSession, candidate, foreign_candidate
):
    service: SkillService = await get_skill_service(session)
    fc = foreign_candidate["candidate"]
    fs = foreign_candidate["skill"]
    owner = candidate.user_id

    with pytest.raises(NotFoundError):
        await service.update(fc.id, owner, fs.id, SkillUpdate(name="Renamed"))

    from backend.repositories.skill import SkillRepository

    refreshed = await SkillRepository(session).get(fs.id)
    assert refreshed is not None
    assert refreshed.name == "Java"
