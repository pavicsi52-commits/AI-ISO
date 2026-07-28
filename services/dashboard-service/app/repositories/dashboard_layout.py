"""Repository for :class:`app.models.dashboard_layout.DashboardLayout`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard_layout import DashboardLayout
from app.models.enums import LayoutBreakpoint


class DashboardLayoutRepository(BaseRepository[DashboardLayout]):
    """CRUD plus lookups for :class:`DashboardLayout`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DashboardLayout, tenant_scope=tenant_scope)

    async def get_current(
        self, dashboard_id: UUID, breakpoint_: LayoutBreakpoint
    ) -> DashboardLayout | None:
        """The layout currently in force for one breakpoint."""
        stmt = self._base_select().where(
            DashboardLayout.dashboard_id == dashboard_id,
            DashboardLayout.breakpoint == breakpoint_,
            DashboardLayout.is_current.is_(True),
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_revisions(
        self, dashboard_id: UUID, breakpoint_: LayoutBreakpoint, *, limit: int = 50
    ) -> list[DashboardLayout]:
        """Saved revisions for one breakpoint, newest first.

        Bounded: undo history grows without limit, and a UI only ever
        shows the recent stack.
        """
        stmt = (
            self._base_select()
            .where(
                DashboardLayout.dashboard_id == dashboard_id,
                DashboardLayout.breakpoint == breakpoint_,
            )
            .order_by(desc(DashboardLayout.revision))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_revision(
        self, dashboard_id: UUID, breakpoint_: LayoutBreakpoint, revision: int
    ) -> DashboardLayout | None:
        """One specific saved revision."""
        stmt = self._base_select().where(
            DashboardLayout.dashboard_id == dashboard_id,
            DashboardLayout.breakpoint == breakpoint_,
            DashboardLayout.revision == revision,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_dashboard(self, dashboard_id: UUID) -> list[DashboardLayout]:
        """Every current layout, across all breakpoints."""
        stmt = self._base_select().where(
            DashboardLayout.dashboard_id == dashboard_id,
            DashboardLayout.is_current.is_(True),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def next_revision(self, dashboard_id: UUID, breakpoint_: LayoutBreakpoint) -> int:
        """The next revision number, computed as ``MAX + 1`` in SQL.

        Using the maximum rather than a count so a pruned intermediate
        revision can never collide with an existing row.
        """
        stmt = (
            self._base_select()
            .with_only_columns(func.max(DashboardLayout.revision))
            .where(
                DashboardLayout.dashboard_id == dashboard_id,
                DashboardLayout.breakpoint == breakpoint_,
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one_or_none() or 0) + 1


__all__ = ["DashboardLayoutRepository"]
