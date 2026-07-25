"""Repository for :class:`app.models.configuration_rollback.ConfigurationRollback`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration_rollback import ConfigurationRollback


class ConfigurationRollbackRepository(BaseRepository[ConfigurationRollback]):
    """CRUD plus lookup for :class:`ConfigurationRollback`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConfigurationRollback, tenant_scope=tenant_scope)

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationRollback]:
        """Every rollback recorded for *profile_id*, newest first ("Rollback History")."""
        stmt = (
            self._base_select()
            .where(ConfigurationRollback.profile_id == profile_id)
            .order_by(desc(ConfigurationRollback.created_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ConfigurationRollbackRepository"]
