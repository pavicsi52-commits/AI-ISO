"""Repository for :class:`app.models.alert_route.AlertRoute`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_route import AlertRoute


class AlertRouteRepository(BaseRepository[AlertRoute]):
    """CRUD plus lookup for :class:`AlertRoute`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AlertRoute, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[AlertRoute]:
        """Every route belonging to *organization_id*."""
        stmt = self._base_select().where(AlertRoute.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_enabled_for_org(self, organization_id: UUID) -> list[AlertRoute]:
        """Every enabled route for *organization_id*.

        Severity filtering is applied in :mod:`app.routing.engine`
        rather than here -- a route with ``severity_filter IS NULL``
        matches every severity, which is a matching *rule*, not a
        query predicate a single ``WHERE`` clause expresses cleanly.
        """
        stmt = self._base_select().where(
            AlertRoute.organization_id == organization_id, AlertRoute.enabled.is_(True)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AlertRouteRepository"]
