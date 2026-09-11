"""Raw job extraction repository."""

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.raw_job_extraction import RawJobExtraction
from backend.repositories.base import BaseRepository


class RawJobExtractionRepository(BaseRepository[RawJobExtraction]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RawJobExtraction)
