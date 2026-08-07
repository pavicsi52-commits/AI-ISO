"""Repository for :class:`app.models.marketplace.AgentMarketplaceEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AgentMarketplaceListingStatus
from app.models.marketplace import AgentMarketplaceEntry


class AgentMarketplaceEntryRepository(BaseRepository[AgentMarketplaceEntry]):
    """CRUD plus lookup for :class:`AgentMarketplaceEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AgentMarketplaceEntry, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, entry_id: UUID) -> AgentMarketplaceEntry:
        """Return *entry_id*, scoped to *organization_id*.

        Raises:
            NotFoundError: If no such listing exists in that organization.
        """
        stmt = self._base_select().where(
            AgentMarketplaceEntry.id == entry_id,
            AgentMarketplaceEntry.organization_id == organization_id,
        )
        result = await self._session.execute(stmt)
        found = result.scalars().first()
        if found is None:
            raise NotFoundError(
                f"AgentMarketplaceEntry {entry_id!s} was not found in organization "
                f"{organization_id!s}."
            )
        return found

    async def get_for_agent(self, agent_id: UUID) -> AgentMarketplaceEntry | None:
        """Return *agent_id*'s own listing, if it has one."""
        stmt = self._base_select().where(AgentMarketplaceEntry.agent_id == agent_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_published(self, organization_id: UUID) -> list[AgentMarketplaceEntry]:
        """Every ``PUBLISHED``/``FEATURED`` listing in *organization_id*,
        featured first."""
        stmt = (
            self._base_select()
            .where(
                AgentMarketplaceEntry.organization_id == organization_id,
                AgentMarketplaceEntry.status.in_(
                    (
                        AgentMarketplaceListingStatus.PUBLISHED,
                        AgentMarketplaceListingStatus.FEATURED,
                    )
                ),
            )
            .order_by(AgentMarketplaceEntry.featured.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AgentMarketplaceEntryRepository"]
