"""``plugin_statistics``, ``plugin_reports``, and ``plugin_audit`` repositories."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuditAction, ReportKind
from app.models.governance import PluginAudit, PluginReport, PluginStatistic


class PluginStatisticRepository(BaseRepository[PluginStatistic]):
    """Rolled-up marketplace activity windows, one row per organization per window."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PluginStatistic, tenant_scope=tenant_scope)

    async def get_for_window(
        self, organization_id: UUID, window_start: datetime
    ) -> PluginStatistic | None:
        """This organization's own rolled-up row for one window start, if computed already."""
        stmt = (
            self._base_select()
            .where(PluginStatistic.organization_id == organization_id)
            .where(PluginStatistic.window_start == window_start)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def latest(self, organization_id: UUID) -> PluginStatistic | None:
        """This organization's own most recently rolled-up window, if any exist yet."""
        stmt = (
            self._base_select()
            .where(PluginStatistic.organization_id == organization_id)
            .order_by(PluginStatistic.window_end.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_since(self, organization_id: UUID, *, since: datetime) -> list[PluginStatistic]:
        """This organization's own windows starting at or after *since*, oldest first."""
        stmt = (
            self._base_select()
            .where(PluginStatistic.organization_id == organization_id)
            .where(PluginStatistic.window_start >= since)
            .order_by(PluginStatistic.window_start)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class PluginReportRepository(BaseRepository[PluginReport]):
    """Generated reports."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PluginReport, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, report_id: UUID) -> PluginReport:
        """One report by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(PluginReport.organization_id == organization_id)
            .where(PluginReport.id == report_id)
        )
        result = await self._session.execute(stmt)
        found: PluginReport | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No report with id {report_id} in this organization.")
        return found

    async def list_for_org(
        self, organization_id: UUID, *, kind: ReportKind | None = None, limit: int = 100
    ) -> list[PluginReport]:
        """Reports generated in this organization, newest first."""
        stmt = self._base_select().where(PluginReport.organization_id == organization_id)
        if kind is not None:
            stmt = stmt.where(PluginReport.kind == kind)
        stmt = stmt.order_by(PluginReport.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class PluginAuditRepository(BaseRepository[PluginAudit]):
    """The append-only audit trail."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PluginAudit, tenant_scope=tenant_scope)

    async def list_for_entity(self, entity_type: str, entity_id: UUID) -> list[PluginAudit]:
        """Every audit row for one entity, newest first."""
        stmt = (
            self._base_select()
            .where(PluginAudit.entity_type == entity_type)
            .where(PluginAudit.entity_id == entity_id)
            .order_by(PluginAudit.occurred_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        action: AuditAction | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[PluginAudit]:
        """This organization's own audit trail, newest first."""
        stmt = self._base_select().where(PluginAudit.organization_id == organization_id)
        if action is not None:
            stmt = stmt.where(PluginAudit.action == action)
        stmt = stmt.order_by(PluginAudit.occurred_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_action(self, organization_id: UUID, *, since: datetime) -> dict[str, int]:
        """How many audit rows of each action have landed since *since*."""
        stmt = (
            self._base_select()
            .where(PluginAudit.organization_id == organization_id)
            .where(PluginAudit.occurred_at >= since)
        )
        result = await self._session.execute(stmt)
        counts: dict[str, int] = {}
        for row in result.scalars().all():
            key = str(row.action)
            counts[key] = counts.get(key, 0) + 1
        return counts


__all__ = ["PluginAuditRepository", "PluginReportRepository", "PluginStatisticRepository"]
