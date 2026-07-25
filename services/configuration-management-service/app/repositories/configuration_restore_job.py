"""Repository for :class:`app.models.configuration_restore_job.ConfigurationRestoreJob`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration_restore_job import ConfigurationRestoreJob


class ConfigurationRestoreJobRepository(BaseRepository[ConfigurationRestoreJob]):
    """CRUD plus lookup for :class:`ConfigurationRestoreJob`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConfigurationRestoreJob, tenant_scope=tenant_scope)

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationRestoreJob]:
        """Every restore job recorded for *profile_id*."""
        stmt = self._base_select().where(ConfigurationRestoreJob.profile_id == profile_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ConfigurationRestoreJobRepository"]
