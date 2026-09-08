"""Generic async repository base."""

from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

T = TypeVar("T", bound=SQLModel)


class BaseRepository[T]:
    """CRUD helper for SQLModel models."""

    def __init__(self, session: AsyncSession, model: type[T]) -> None:
        self.session = session
        self.model = model

    async def get(self, obj_id: UUID) -> T | None:
        return await self.session.get(self.model, obj_id)

    async def get_or_404(self, obj_id: UUID) -> T:
        obj = await self.get(obj_id)
        if obj is None:
            from backend.core.exceptions import NotFoundError

            raise NotFoundError(f"{self.model.__name__} not found")
        return obj

    async def list(self, **filters: Any) -> list[T]:
        stmt = select(self.model)
        for key, value in filters.items():
            if value is not None and hasattr(self.model, key):
                stmt = stmt.where(getattr(self.model, key) == value)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, **data: Any) -> T:
        obj = self.model(**data)
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def update(self, obj: T, **data: Any) -> T:
        for key, value in data.items():
            setattr(obj, key, value)
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def delete(self, obj: T) -> None:
        await self.session.delete(obj)
        await self.session.flush()
