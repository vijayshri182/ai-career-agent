"""Approval workflow repositories."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models.approval import Approval, ApprovalDecision, ApprovalKind, ApprovalStatus
from backend.repositories.base import BaseRepository


class ApprovalRepository(BaseRepository[Approval]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Approval)

    async def get_for_candidate(self, approval_id: UUID, candidate_id: UUID) -> Approval | None:
        stmt = select(Approval).where(
            Approval.id == approval_id,
            Approval.candidate_id == candidate_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_candidate_detailed(
        self, approval_id: UUID, candidate_id: UUID
    ) -> Approval | None:
        stmt = (
            select(Approval)
            .where(
                Approval.id == approval_id,
                Approval.candidate_id == candidate_id,
            )
            .options(selectinload(Approval.decisions))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_open_for_target(
        self,
        candidate_id: UUID,
        kind: ApprovalKind,
        target_type: str,
        target_id: UUID,
    ) -> Approval | None:
        stmt = select(Approval).where(
            Approval.candidate_id == candidate_id,
            Approval.kind == kind,
            Approval.target_type == target_type,
            Approval.target_id == target_id,
            Approval.status.in_([ApprovalStatus.PENDING, ApprovalStatus.SNOOZED]),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_approved_for_target(
        self,
        candidate_id: UUID,
        kind: ApprovalKind,
        target_type: str,
        target_id: UUID,
    ) -> Approval | None:
        stmt = (
            select(Approval)
            .where(
                Approval.candidate_id == candidate_id,
                Approval.kind == kind,
                Approval.target_type == target_type,
                Approval.target_id == target_id,
                Approval.status == ApprovalStatus.APPROVED,
            )
            .order_by(Approval.__table__.c.decided_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_for_candidate(
        self,
        candidate_id: UUID,
        *,
        status: ApprovalStatus | None = None,
        kind: ApprovalKind | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Approval]:
        stmt = select(Approval).where(Approval.candidate_id == candidate_id)
        if status is not None:
            stmt = stmt.where(Approval.status == status)
        if kind is not None:
            stmt = stmt.where(Approval.kind == kind)
        stmt = (
            stmt.order_by(Approval.__table__.c.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_candidate(
        self,
        candidate_id: UUID,
        *,
        status: ApprovalStatus | None = None,
        kind: ApprovalKind | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(Approval).where(
            Approval.candidate_id == candidate_id
        )
        if status is not None:
            stmt = stmt.where(Approval.status == status)
        if kind is not None:
            stmt = stmt.where(Approval.kind == kind)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())


class ApprovalDecisionRepository(BaseRepository[ApprovalDecision]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ApprovalDecision)

    async def list_for_approval(self, approval_id: UUID) -> list[ApprovalDecision]:
        stmt = (
            select(ApprovalDecision)
            .where(ApprovalDecision.approval_id == approval_id)
            .order_by(ApprovalDecision.__table__.c.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
