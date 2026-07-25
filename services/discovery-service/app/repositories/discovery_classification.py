"""Repository for :class:`app.models.discovery_classification.DiscoveryClassificationEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_classification import DiscoveryClassificationEntry


class DiscoveryClassificationRepository(BaseRepository[DiscoveryClassificationEntry]):
    """CRUD plus lookup for :class:`DiscoveryClassificationEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DiscoveryClassificationEntry, tenant_scope=tenant_scope)

    async def list_for_asset(self, discovery_asset_id: UUID) -> list[DiscoveryClassificationEntry]:
        """Every classification decision for *discovery_asset_id*, newest first."""
        stmt = (
            self._base_select()
            .where(DiscoveryClassificationEntry.discovery_asset_id == discovery_asset_id)
            .order_by(desc(DiscoveryClassificationEntry.created_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["DiscoveryClassificationRepository"]
