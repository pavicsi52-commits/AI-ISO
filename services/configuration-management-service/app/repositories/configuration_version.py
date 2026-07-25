"""Repository for :class:`app.models.configuration_version.ConfigurationVersion`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration_version import ConfigurationVersion


class ConfigurationVersionRepository(BaseRepository[ConfigurationVersion]):
    """CRUD plus lookup for :class:`ConfigurationVersion`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConfigurationVersion, tenant_scope=tenant_scope)

    async def list_for_profile(
        self, profile_id: UUID, *, branch: str | None = None
    ) -> list[ConfigurationVersion]:
        """Every version recorded for *profile_id*, newest first, optionally
        narrowed to a single *branch* ("Branching").
        """
        stmt = self._base_select().where(ConfigurationVersion.profile_id == profile_id)
        if branch is not None:
            stmt = stmt.where(ConfigurationVersion.branch == branch)
        stmt = stmt.order_by(desc(ConfigurationVersion.created_at))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_for_profile(
        self, profile_id: UUID, *, branch: str = "main"
    ) -> ConfigurationVersion | None:
        """Return *profile_id*'s most recently created version on *branch*, or ``None``."""
        stmt = (
            self._base_select()
            .where(
                ConfigurationVersion.profile_id == profile_id,
                ConfigurationVersion.branch == branch,
            )
            .order_by(desc(ConfigurationVersion.created_at))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["ConfigurationVersionRepository"]
