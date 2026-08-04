"""The maintenance window repository."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.maintenance import MaintenanceWindow


class MaintenanceWindowRepository(BaseRepository[MaintenanceWindow]):
    """Periods that suppress or override job dispatch."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, MaintenanceWindow, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, window_id: UUID) -> MaintenanceWindow:
        """One window by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(MaintenanceWindow.organization_id == organization_id)
            .where(MaintenanceWindow.id == window_id)
        )
        result = await self._session.execute(stmt)
        found: MaintenanceWindow | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No maintenance window with id {window_id} in this organization.")
        return found

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 200, offset: int = 0
    ) -> list[MaintenanceWindow]:
        """Every window this organization has defined, soonest first."""
        stmt = (
            self._base_select()
            .where(MaintenanceWindow.organization_id == organization_id)
            .order_by(MaintenanceWindow.starts_at)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_active_at(
        self, organization_id: UUID, *, moment: datetime, limit: int = 200
    ) -> list[MaintenanceWindow]:
        """Every window whose ``[starts_at, ends_at)`` covers *moment*.

        Recurring windows are matched only on their stored (first
        occurrence) bounds -- a caller checking a moment far from the
        window's own creation should expand its recurrence first, the
        same division of responsibility
        ``services/change-management-service``'s own calendar
        repository/engine split establishes.
        """
        stmt = (
            self._base_select()
            .where(MaintenanceWindow.organization_id == organization_id)
            .where(MaintenanceWindow.starts_at <= moment)
            .where(MaintenanceWindow.ends_at > moment)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["MaintenanceWindowRepository"]
