"""``plugin_statistics``, ``plugin_reports``, and ``plugin_audit`` repositories."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuditAction, ReportKind
from app.models.governance import PluginAudit, PluginReport, PluginStatistic


class PluginStatisticRepository(BaseRepository[PluginStatistic]):
    """Rolled-up marketplace activity windows."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PluginStatistic, tenant_scope=tenant_scope)

    async def list_between(self, start: datetime, end: datetime) -> list[PluginStatistic]:
        """Every rolled-up window overlapping ``[start, end]``, oldest first."""
        stmt = (
            self._base_select()
            .where(PluginStatistic.window_start >= start)
            .where(PluginStatistic.window_end <= end)
            .order_by(PluginStatistic.window_start)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest(self) -> PluginStatistic | None:
        """The most recently rolled-up statistics window, if any exist yet."""
        stmt = self._base_select().order_by(PluginStatistic.window_end.desc()).limit(1)
        result = await self._session.execute(stmt)
        return result.scalars().first()


class PluginReportRepository(BaseRepository[PluginReport]):
    """Generated reports."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PluginReport, tenant_scope=tenant_scope)

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


__all__ = ["PluginAuditRepository", "PluginReportRepository", "PluginStatisticRepository"]
