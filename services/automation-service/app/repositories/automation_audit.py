"""Repository for :class:`app.models.automation_audit.AutomationAuditEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_audit import AutomationAuditEntry


class AutomationAuditRepository(BaseRepository[AutomationAuditEntry]):
    """CRUD plus lookup for :class:`AutomationAuditEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AutomationAuditEntry, tenant_scope=tenant_scope)

    async def list_for_job(self, job_id: UUID) -> list[AutomationAuditEntry]:
        """Every audit entry for *job_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AutomationAuditEntry.job_id == job_id)
            .order_by(desc(AutomationAuditEntry.created_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_execution(self, execution_id: UUID) -> list[AutomationAuditEntry]:
        """Every audit entry for *execution_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AutomationAuditEntry.execution_id == execution_id)
            .order_by(desc(AutomationAuditEntry.created_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AutomationAuditRepository"]
