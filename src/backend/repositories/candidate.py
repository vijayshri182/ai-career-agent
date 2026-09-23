"""Candidate repository."""

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import NotFoundError
from backend.core.security_service import get_security_service
from backend.models.candidate import Candidate, ProfileStatus
from backend.repositories.base import BaseRepository


class CandidateRepository(BaseRepository[Candidate]):
    """Repository for candidate profiles, including PII field handling."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Candidate)
        self.security = get_security_service()

    async def get_by_user(self, user_id: UUID) -> Candidate | None:
        stmt = select(Candidate).where(Candidate.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_user(self, user_id: UUID) -> Candidate | None:
        stmt = select(Candidate).where(
            Candidate.user_id == user_id, Candidate.status != ProfileStatus.DELETED
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_user_or_404(self, candidate_id: UUID, user_id: UUID) -> Candidate:
        candidate = await self.get(candidate_id)
        if candidate is None or candidate.user_id != user_id:
            raise NotFoundError("Candidate not found")
        return candidate

    async def list_active(self) -> list[Candidate]:
        stmt = select(Candidate).where(Candidate.status != ProfileStatus.DELETED)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    def _prepare_pii(self, data: dict[str, object]) -> dict[str, object]:
        """Map plain PII fields to encrypted storage columns + email hash."""
        if "email" in data and data["email"] is not None:
            plain_email = str(data.pop("email"))
            data["email_encrypted"] = self.security.encrypt(plain_email)
            data["email_hash"] = self.security.hash_email(plain_email)
        elif "email" in data:
            data["email_encrypted"] = None
            data["email_hash"] = None

        # The model exposes `email` and `phone` through properties that
        # decrypt a second time, so these two fields are stored with an
        # outer encryption layer here, while the EncryptedString column
        # type adds the inner layer on bind. Matching layers let the
        # properties return plaintext.
        if "phone" in data and data["phone"] is not None:
            plain_phone = str(data.pop("phone"))
            data["phone_encrypted"] = self.security.encrypt(plain_phone)
        elif "phone" in data:
            data["phone_encrypted"] = None

        if "current_location" in data:
            # The `current_location` property decrypts the column value a second
            # time, so like email/phone this is stored with an outer ciphertext
            # layer that balances the property's extra decrypt.
            location = data.pop("current_location")
            data["current_location_json"] = (
                self.security.encrypt(json.dumps(location)) if location is not None else None
            )
        return data

    async def create_for_user(self, user_id: UUID, **data: Any) -> Candidate:
        data["user_id"] = user_id
        data = self._prepare_pii(data)
        return await super().create(**data)

    async def update_candidate(self, candidate: Candidate, **data: Any) -> Candidate:
        data = self._prepare_pii(data)
        return await super().update(candidate, **data)
