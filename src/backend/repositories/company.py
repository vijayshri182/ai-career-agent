"""Company repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.company import Company
from backend.repositories.base import BaseRepository


class CompanyRepository(BaseRepository[Company]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Company)

    async def find_by_domain(self, domain: str | None) -> Company | None:
        if not domain:
            return None
        stmt = select(Company).where(Company.website_domain == domain)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_or_create_by_domain(self, name: str, domain: str | None) -> Company:
        existing = await self.find_by_domain(domain)
        if existing is not None:
            return existing
        return await self.create(name=name, website_domain=domain)
