"""Repository for :class:`app.models.monitoring_target.MonitoringTarget`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MonitoringTargetType
from app.models.monitoring_target import MonitoringTarget


class MonitoringTargetRepository(BaseRepository[MonitoringTarget]):
    """CRUD plus lookup for :class:`MonitoringTarget`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, MonitoringTarget, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[MonitoringTarget]:
        """Every monitoring target belonging to *organization_id*."""
        stmt = self._base_select().where(MonitoringTarget.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_ids(self, target_ids: list[UUID]) -> list[MonitoringTarget]:
        """Resolve a list of target ids into their actual rows."""
        if not target_ids:
            return []
        stmt = self._base_select().where(MonitoringTarget.id.in_(target_ids))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_external_id(
        self, organization_id: UUID, target_type: MonitoringTargetType, external_id: str
    ) -> MonitoringTarget | None:
        """Return the target already registered for this external asset, if any.

        Lets callers re-monitor the same inventory asset/workflow
        instance/etc. across many collections without registering a
        fresh duplicate :class:`MonitoringTarget` row every time.
        """
        stmt = self._base_select().where(
            MonitoringTarget.organization_id == organization_id,
            MonitoringTarget.target_type == target_type,
            MonitoringTarget.external_id == external_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["MonitoringTargetRepository"]
