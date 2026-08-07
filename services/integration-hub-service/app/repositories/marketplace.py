"""``connector_marketplace`` repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MarketplaceStatus
from app.models.marketplace import ConnectorMarketplaceEntry


class ConnectorMarketplaceRepository(BaseRepository[ConnectorMarketplaceEntry]):
    """The connector catalog."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConnectorMarketplaceEntry, tenant_scope=tenant_scope)

    async def require_in_org(
        self, organization_id: UUID, entry_id: UUID
    ) -> ConnectorMarketplaceEntry:
        """One catalog entry by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ConnectorMarketplaceEntry.organization_id == organization_id)
            .where(ConnectorMarketplaceEntry.id == entry_id)
        )
        result = await self._session.execute(stmt)
        found: ConnectorMarketplaceEntry | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No marketplace entry with id {entry_id} in this organization.")
        return found

    async def get_by_slug(
        self, organization_id: UUID, slug: str
    ) -> ConnectorMarketplaceEntry | None:
        """One catalog entry by its own unique ``slug``, if it exists in this organization."""
        stmt = (
            self._base_select()
            .where(ConnectorMarketplaceEntry.organization_id == organization_id)
            .where(ConnectorMarketplaceEntry.slug == slug)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        category: str | None = None,
        status: MarketplaceStatus | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ConnectorMarketplaceEntry]:
        """Catalog entries visible in this organization, alphabetical by name."""
        stmt = self._base_select().where(
            ConnectorMarketplaceEntry.organization_id == organization_id
        )
        if category is not None:
            stmt = stmt.where(ConnectorMarketplaceEntry.category == category)
        if status is not None:
            stmt = stmt.where(ConnectorMarketplaceEntry.status == str(status))
        stmt = stmt.order_by(ConnectorMarketplaceEntry.name).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ConnectorMarketplaceRepository"]
