"""Repository for :class:`app.models.alert_maintenance_window.AlertMaintenanceWindow`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_maintenance_window import AlertMaintenanceWindow


class AlertMaintenanceWindowRepository(BaseRepository[AlertMaintenanceWindow]):
    """CRUD plus lookup for :class:`AlertMaintenanceWindow`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AlertMaintenanceWindow, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[AlertMaintenanceWindow]:
        """Every maintenance window belonging to *organization_id*."""
        stmt = self._base_select().where(AlertMaintenanceWindow.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_enabled_for_org(self, organization_id: UUID) -> list[AlertMaintenanceWindow]:
        """Every enabled maintenance window for *organization_id*.

        Deliberately does NOT filter by ``starts_at``/``ends_at`` in
        SQL: a ``RECURRING`` window's own stored interval is only its
        *first* occurrence, and whether it is in force right now is a
        recurrence-rule computation
        (:func:`app.suppression.maintenance.is_window_active`), not a
        column comparison.
        """
        stmt = self._base_select().where(
            AlertMaintenanceWindow.organization_id == organization_id,
            AlertMaintenanceWindow.enabled.is_(True),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AlertMaintenanceWindowRepository"]

# Deliberately NO ``list_active_at(organization_id, moment)`` SQL helper
# here. Such a method reads as the obvious way to ask "which windows are
# in force now", but a ``RECURRING`` window's own stored
# ``starts_at``/``ends_at`` describe only its *first* occurrence -- a
# plain column comparison would silently miss every later one. Whether a
# window is in force is a recurrence computation
# (:func:`app.suppression.maintenance.is_window_active`, applied by
# :meth:`app.services.maintenance_window.AlertMaintenanceWindowService
# .list_active` over :meth:`list_enabled_for_org`). Leaving the tempting
# shortcut out is the point.
