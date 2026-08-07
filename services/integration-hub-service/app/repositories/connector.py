"""``connectors``, ``connector_categories``, and ``connector_versions`` repositories."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connector import Connector, ConnectorCategoryEntry, ConnectorVersion
from app.models.enums import ConnectorLifecycleStatus


class ConnectorRepository(BaseRepository[Connector]):
    """Organization-owned connector instances."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, Connector, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, connector_id: UUID) -> Connector:
        """One connector by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(Connector.organization_id == organization_id)
            .where(Connector.id == connector_id)
        )
        result = await self._session.execute(stmt)
        found: Connector | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No connector with id {connector_id} in this organization.")
        return found

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        category: str | None = None,
        status: ConnectorLifecycleStatus | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Connector]:
        """Connectors in this organization, newest first."""
        stmt = self._base_select().where(Connector.organization_id == organization_id)
        if category is not None:
            stmt = stmt.where(Connector.category == category)
        if status is not None:
            stmt = stmt.where(Connector.status == str(status))
        stmt = stmt.order_by(Connector.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all_enabled(self, *, limit: int = 500) -> list[Connector]:
        """Every enabled connector across every organization -- for the health-probe sweep."""
        stmt = self._base_select().where(Connector.enabled.is_(True)).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class ConnectorCategoryRepository(BaseRepository[ConnectorCategoryEntry]):
    """Connector categories, built-in and custom."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConnectorCategoryEntry, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[ConnectorCategoryEntry]:
        """Categories visible in this organization."""
        stmt = (
            self._base_select()
            .where(ConnectorCategoryEntry.organization_id == organization_id)
            .order_by(ConnectorCategoryEntry.name)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name(self, organization_id: UUID, name: str) -> ConnectorCategoryEntry | None:
        """One category by its own name, if registered in this organization."""
        stmt = (
            self._base_select()
            .where(ConnectorCategoryEntry.organization_id == organization_id)
            .where(ConnectorCategoryEntry.name == name)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


class ConnectorVersionRepository(BaseRepository[ConnectorVersion]):
    """A connector instance's own upgrade/rollback history."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConnectorVersion, tenant_scope=tenant_scope)

    async def list_for_connector(self, connector_id: UUID) -> list[ConnectorVersion]:
        """Every version of one connector, newest first."""
        stmt = (
            self._base_select()
            .where(ConnectorVersion.connector_id == connector_id)
            .order_by(ConnectorVersion.installed_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_current(self, connector_id: UUID) -> ConnectorVersion | None:
        """The connector's own currently-installed version row, if any."""
        stmt = (
            self._base_select()
            .where(ConnectorVersion.connector_id == connector_id)
            .where(ConnectorVersion.is_current.is_(True))
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["ConnectorCategoryRepository", "ConnectorRepository", "ConnectorVersionRepository"]
