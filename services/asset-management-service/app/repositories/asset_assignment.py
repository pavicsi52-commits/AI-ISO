"""Repository for :class:`app.models.asset_assignment.AssetAssignment`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_assignment import AssetAssignment
from app.models.enums import AssignmentStatus


class AssetAssignmentRepository(BaseRepository[AssetAssignment]):
    """CRUD plus lookup for :class:`AssetAssignment`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetAssignment, tenant_scope=tenant_scope)

    async def list_for_managed_asset(self, managed_asset_id: UUID) -> list[AssetAssignment]:
        """Every assignment recorded for *managed_asset_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AssetAssignment.managed_asset_id == managed_asset_id)
            .order_by(desc(AssetAssignment.assigned_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_for_managed_asset(self, managed_asset_id: UUID) -> AssetAssignment | None:
        """Return *managed_asset_id*'s current active assignment, or ``None``."""
        stmt = self._base_select().where(
            AssetAssignment.managed_asset_id == managed_asset_id,
            AssetAssignment.status == AssignmentStatus.ACTIVE,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_assignee(self, assignee_id: UUID) -> list[AssetAssignment]:
        """Every assignment held by *assignee_id*."""
        stmt = self._base_select().where(AssetAssignment.assignee_id == assignee_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetAssignmentRepository"]
