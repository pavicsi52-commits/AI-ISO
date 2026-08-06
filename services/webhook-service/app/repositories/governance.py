"""The webhook statistics, report, and audit repositories."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuditAction
from app.models.governance import WebhookAudit, WebhookReport, WebhookStatistic


class WebhookStatisticRepository(BaseRepository[WebhookStatistic]):
    """Rolled-up traffic windows."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WebhookStatistic, tenant_scope=tenant_scope)

    async def get_for_window(
        self, organization_id: UUID, window_start: datetime
    ) -> WebhookStatistic | None:
        """The statistics row already computed for this exact window start, if any."""
        stmt = (
            self._base_select()
            .where(WebhookStatistic.organization_id == organization_id)
            .where(WebhookStatistic.window_start == window_start)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def latest(self, organization_id: UUID) -> WebhookStatistic | None:
        """The most recently computed window for this organization, if any."""
        stmt = (
            self._base_select()
            .where(WebhookStatistic.organization_id == organization_id)
            .order_by(WebhookStatistic.window_start.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_since(self, organization_id: UUID, *, since: datetime) -> list[WebhookStatistic]:
        """Windows since *since*, oldest first."""
        stmt = (
            self._base_select()
            .where(WebhookStatistic.organization_id == organization_id)
            .where(WebhookStatistic.window_start >= since)
            .order_by(WebhookStatistic.window_start)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class WebhookReportRepository(BaseRepository[WebhookReport]):
    """Generated reports."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WebhookReport, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, report_id: UUID) -> WebhookReport:
        """One report by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(WebhookReport.organization_id == organization_id)
            .where(WebhookReport.id == report_id)
        )
        result = await self._session.execute(stmt)
        found: WebhookReport | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No report with id {report_id} in this organization.")
        return found

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 200, offset: int = 0
    ) -> list[WebhookReport]:
        """Reports, newest first."""
        stmt = (
            self._base_select()
            .where(WebhookReport.organization_id == organization_id)
            .order_by(WebhookReport.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class WebhookAuditRepository(BaseRepository[WebhookAudit]):
    """The append-only audit trail."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WebhookAudit, tenant_scope=tenant_scope)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        action: AuditAction | None = None,
        entity_id: UUID | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[WebhookAudit]:
        """Audit entries, newest first."""
        stmt = self._base_select().where(WebhookAudit.organization_id == organization_id)
        if action is not None:
            stmt = stmt.where(WebhookAudit.action == str(action))
        if entity_id is not None:
            stmt = stmt.where(WebhookAudit.entity_id == entity_id)
        stmt = stmt.order_by(WebhookAudit.occurred_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_action(self, organization_id: UUID, *, since: datetime) -> dict[str, int]:
        """How many audit entries of each action have happened since *since*."""
        stmt = (
            self._base_select()
            .where(WebhookAudit.organization_id == organization_id)
            .where(WebhookAudit.occurred_at >= since)
            .with_only_columns(WebhookAudit.action, func.count())
            .group_by(WebhookAudit.action)
        )
        result = await self._session.execute(stmt)
        return {str(action): count for action, count in result.all()}


__all__ = ["WebhookAuditRepository", "WebhookReportRepository", "WebhookStatisticRepository"]
