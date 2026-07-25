"""Repository for :class:`app.models.inventory_audit.InventoryAuditEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_audit import InventoryAuditEntry


class InventoryAuditRepository(BaseRepository[InventoryAuditEntry]):
    """CRUD plus lookup for :class:`InventoryAuditEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, InventoryAuditEntry, tenant_scope=tenant_scope)

    async def list_for_asset(self, asset_id: UUID) -> list[InventoryAuditEntry]:
        """Every audit entry for *asset_id*, newest first."""
        stmt = (
            self._base_select()
            .where(InventoryAuditEntry.asset_id == asset_id)
            .order_by(desc(InventoryAuditEntry.created_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["InventoryAuditRepository"]
