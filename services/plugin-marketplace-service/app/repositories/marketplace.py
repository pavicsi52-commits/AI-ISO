"""``plugin_marketplace`` repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import String, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MarketplaceListingStatus
from app.models.marketplace import PluginMarketplaceEntry


class PluginMarketplaceRepository(BaseRepository[PluginMarketplaceEntry]):
    """Published marketplace listings."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PluginMarketplaceEntry, tenant_scope=tenant_scope)

    async def get_for_plugin(self, plugin_id: UUID) -> PluginMarketplaceEntry | None:
        """The marketplace listing for one plugin, if it has been created yet."""
        stmt = self._base_select().where(PluginMarketplaceEntry.plugin_id == plugin_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_published(
        self,
        *,
        search: str | None = None,
        featured_only: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> list[PluginMarketplaceEntry]:
        """Every listing visible in the public marketplace, newest first."""
        stmt = self._base_select().where(
            PluginMarketplaceEntry.status.in_(
                (MarketplaceListingStatus.PUBLISHED, MarketplaceListingStatus.FEATURED)
            )
        )
        if featured_only:
            stmt = stmt.where(PluginMarketplaceEntry.status == MarketplaceListingStatus.FEATURED)
        if search:
            like = f"%{search.lower()}%"
            stmt = stmt.where(
                or_(
                    PluginMarketplaceEntry.pricing_summary.ilike(like),
                    PluginMarketplaceEntry.search_keywords.cast(String).ilike(like),
                )
            )
        stmt = (
            stmt.order_by(PluginMarketplaceEntry.install_count.desc()).limit(limit).offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_pending_approval(self, *, limit: int = 200) -> list[PluginMarketplaceEntry]:
        """Every listing awaiting the marketplace-approval sweep."""
        stmt = (
            self._base_select()
            .where(PluginMarketplaceEntry.status == MarketplaceListingStatus.DRAFT)
            .order_by(PluginMarketplaceEntry.created_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["PluginMarketplaceRepository"]
