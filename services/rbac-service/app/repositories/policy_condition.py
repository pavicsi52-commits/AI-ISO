"""Repository for :class:`app.models.policy_condition.PolicyCondition`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy_condition import PolicyCondition


class PolicyConditionRepository(BaseRepository[PolicyCondition]):
    """CRUD plus lookup for :class:`PolicyCondition`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PolicyCondition, tenant_scope=tenant_scope)

    async def list_for_policy(self, policy_id: UUID) -> list[PolicyCondition]:
        """Every condition attached to *policy_id*."""
        stmt = self._base_select().where(PolicyCondition.policy_id == policy_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["PolicyConditionRepository"]
