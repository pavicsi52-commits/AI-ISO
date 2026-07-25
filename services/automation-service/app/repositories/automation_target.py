"""Repository for :class:`app.models.automation_target.AutomationTarget`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_target import AutomationTarget
from app.models.enums import ExecutionTargetType


class AutomationTargetRepository(BaseRepository[AutomationTarget]):
    """CRUD plus lookup for :class:`AutomationTarget`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AutomationTarget, tenant_scope=tenant_scope)

    async def list_for_org(
        self, organization_id: UUID, *, target_type: ExecutionTargetType | None = None
    ) -> list[AutomationTarget]:
        """Every target belonging to *organization_id*, optionally
        narrowed to a single *target_type*.
        """
        stmt = self._base_select().where(AutomationTarget.organization_id == organization_id)
        if target_type is not None:
            stmt = stmt.where(AutomationTarget.target_type == target_type)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_ids(self, target_ids: list[UUID]) -> list[AutomationTarget]:
        """Every target among *target_ids* that still exists and is active."""
        if not target_ids:
            return []
        stmt = self._base_select().where(AutomationTarget.id.in_(target_ids))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AutomationTargetRepository"]
