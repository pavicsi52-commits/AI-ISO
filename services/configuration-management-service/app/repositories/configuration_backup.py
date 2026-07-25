"""Repository for :class:`app.models.configuration_backup.ConfigurationBackup`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration_backup import ConfigurationBackup


class ConfigurationBackupRepository(BaseRepository[ConfigurationBackup]):
    """CRUD plus lookup for :class:`ConfigurationBackup`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConfigurationBackup, tenant_scope=tenant_scope)

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationBackup]:
        """Every backup recorded for *profile_id*, newest first."""
        stmt = (
            self._base_select()
            .where(ConfigurationBackup.profile_id == profile_id)
            .order_by(desc(ConfigurationBackup.created_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_for_profile(self, profile_id: UUID) -> ConfigurationBackup | None:
        """Return *profile_id*'s most recently created backup, or ``None``."""
        stmt = (
            self._base_select()
            .where(ConfigurationBackup.profile_id == profile_id)
            .order_by(desc(ConfigurationBackup.created_at))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["ConfigurationBackupRepository"]
