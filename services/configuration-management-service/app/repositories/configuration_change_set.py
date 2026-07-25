"""Repository for :class:`app.models.configuration_change_set.ConfigurationChangeSet`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration_change_set import ConfigurationChangeSet


class ConfigurationChangeSetRepository(BaseRepository[ConfigurationChangeSet]):
    """CRUD plus lookup for :class:`ConfigurationChangeSet`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConfigurationChangeSet, tenant_scope=tenant_scope)

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationChangeSet]:
        """Every change set recorded for *profile_id*, newest first."""
        stmt = (
            self._base_select()
            .where(ConfigurationChangeSet.profile_id == profile_id)
            .order_by(desc(ConfigurationChangeSet.created_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ConfigurationChangeSetRepository"]
