"""Repository for :class:`app.models.discovery_schedule.DiscoverySchedule`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_schedule import DiscoverySchedule


class DiscoveryScheduleRepository(BaseRepository[DiscoverySchedule]):
    """CRUD plus lookup for :class:`DiscoverySchedule`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DiscoverySchedule, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[DiscoverySchedule]:
        """Every schedule defined for *organization_id*."""
        stmt = self._base_select().where(DiscoverySchedule.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_active(self) -> list[DiscoverySchedule]:
        """Every active schedule across every organization -- used only
        at process startup to register each with the scheduler
        framework (see ``app/core/factory.py``'s ``_lifespan``).
        """
        stmt = self._base_select().where(DiscoverySchedule.is_enabled.is_(True))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_due(self, *, as_of: datetime) -> list[DiscoverySchedule]:
        """Every active schedule whose ``next_run_at`` has arrived."""
        stmt = self._base_select().where(
            DiscoverySchedule.is_enabled.is_(True),
            DiscoverySchedule.next_run_at.is_not(None),
            DiscoverySchedule.next_run_at <= as_of,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["DiscoveryScheduleRepository"]
