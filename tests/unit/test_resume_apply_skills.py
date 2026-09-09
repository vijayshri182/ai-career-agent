"""ResumeService skill merging is case-insensitive and idempotent.

Duplicate skills are merged both within a single extraction and across
repeated applies, so re-applying a parsed resume never duplicates skills.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_extracted_skills_dedup_within_and_across_applies(
    session: AsyncSession, candidate
):
    from backend.api.deps import get_resume_service
    from backend.repositories.skill import SkillRepository

    service = await get_resume_service(session)

    added = await service._apply_extracted_skills(
        candidate, {"skills": ["Java", "java", " Java ", "Kubernetes", "kubernetes"]}
    )
    assert added == ["Java", "Kubernetes"]

    added = await service._apply_extracted_skills(
        candidate, {"skills": ["JAVA", "Docker", " docker "]}
    )
    assert added == ["Docker"]

    added = await service._apply_extracted_skills(
        candidate, {"skills": ["Python", "python", "PYTHON"]}
    )
    assert added == ["Python"]

    skills = await SkillRepository(session).list(candidate_id=candidate.id)
    assert {skill.name for skill in skills} == {"Java", "Kubernetes", "Docker", "Python"}


async def test_empty_skill_extraction_is_noop(session: AsyncSession, candidate):
    from backend.api.deps import get_resume_service

    service = await get_resume_service(session)
    assert await service._apply_extracted_skills(candidate, {"skills": []}) == []
    assert await service._apply_extracted_skills(candidate, {}) == []
