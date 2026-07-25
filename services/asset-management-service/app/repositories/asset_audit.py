"""Repository for :class:`app.models.asset_audit.AssetAuditEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_audit import AssetAuditEntry


class AssetAuditRepository(BaseRepository[AssetAuditEntry]):
    """CRUD plus lookup for :class:`AssetAuditEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetAuditEntry, tenant_scope=tenant_scope)

    async def list_for_managed_asset(self, managed_asset_id: UUID) -> list[AssetAuditEntry]:
        """Every privileged action recorded against *managed_asset_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AssetAuditEntry.managed_asset_id == managed_asset_id)
            .order_by(desc(AssetAuditEntry.created_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetAuditRepository"]
