"""Repository for :class:`app.models.policy_assignment.PolicyAssignment`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SubjectType
from app.models.policy_assignment import PolicyAssignment


class PolicyAssignmentRepository(BaseRepository[PolicyAssignment]):
    """CRUD plus lookup for :class:`PolicyAssignment`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PolicyAssignment, tenant_scope=tenant_scope)

    async def list_for_policy(self, policy_id: UUID) -> list[PolicyAssignment]:
        """Every subject *policy_id* is assigned to."""
        stmt = self._base_select().where(PolicyAssignment.policy_id == policy_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_applicable(
        self, *, subject_type: SubjectType, subject_id: UUID
    ) -> list[PolicyAssignment]:
        """Every assignment that applies to *subject_type*/*subject_id*, plus every
        :attr:`~app.models.enums.SubjectType.GLOBAL` assignment (applies to everyone).
        """
        stmt = self._base_select().where(
            or_(
                (PolicyAssignment.subject_type == subject_type)
                & (PolicyAssignment.subject_id == subject_id),
                PolicyAssignment.subject_type == SubjectType.GLOBAL,
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["PolicyAssignmentRepository"]
