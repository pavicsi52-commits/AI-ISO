"""Repository for :class:`app.models.alert_escalation.AlertEscalationPolicy`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_escalation import AlertEscalationPolicy


class AlertEscalationPolicyRepository(BaseRepository[AlertEscalationPolicy]):
    """CRUD plus lookup for :class:`AlertEscalationPolicy`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AlertEscalationPolicy, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[AlertEscalationPolicy]:
        """Every escalation policy belonging to *organization_id*."""
        stmt = self._base_select().where(AlertEscalationPolicy.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_enabled_for_org(self, organization_id: UUID) -> list[AlertEscalationPolicy]:
        """Every enabled escalation policy for *organization_id*."""
        stmt = self._base_select().where(
            AlertEscalationPolicy.organization_id == organization_id,
            AlertEscalationPolicy.enabled.is_(True),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all_enabled(self) -> list[AlertEscalationPolicy]:
        """Every enabled escalation policy, system-wide.

        Used once at startup to discover which organizations need a
        recurring escalation pass registered -- deliberately
        cross-tenant, since the scheduler is a platform-level concern
        rather than a request served on one organization's behalf.
        """
        stmt = self._base_select().where(AlertEscalationPolicy.enabled.is_(True))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AlertEscalationPolicyRepository"]
