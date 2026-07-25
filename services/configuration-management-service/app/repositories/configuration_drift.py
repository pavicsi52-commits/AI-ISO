"""Repository for :class:`app.models.configuration_drift.ConfigurationDrift`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration_drift import ConfigurationDrift
from app.models.enums import DriftStatus


class ConfigurationDriftRepository(BaseRepository[ConfigurationDrift]):
    """CRUD plus lookup for :class:`ConfigurationDrift`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConfigurationDrift, tenant_scope=tenant_scope)

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationDrift]:
        """Every drift instance detected for *profile_id*, newest first."""
        stmt = (
            self._base_select()
            .where(ConfigurationDrift.profile_id == profile_id)
            .order_by(desc(ConfigurationDrift.detected_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_unresolved_for_org(self, organization_id: UUID) -> list[ConfigurationDrift]:
        """Every not-yet-resolved drift instance for *organization_id*."""
        stmt = self._base_select().where(
            ConfigurationDrift.organization_id == organization_id,
            ConfigurationDrift.status.in_([DriftStatus.DETECTED, DriftStatus.ACKNOWLEDGED]),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ConfigurationDriftRepository"]
