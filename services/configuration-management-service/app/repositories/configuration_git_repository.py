"""Repository for :class:`app.models.configuration_git_repository.ConfigurationGitRepository`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration_git_repository import ConfigurationGitRepository


class ConfigurationGitRepositoryRepository(BaseRepository[ConfigurationGitRepository]):
    """CRUD plus lookup for :class:`ConfigurationGitRepository`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConfigurationGitRepository, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[ConfigurationGitRepository]:
        """Every Git repository registered for *organization_id*."""
        stmt = self._base_select().where(
            ConfigurationGitRepository.organization_id == organization_id
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationGitRepository]:
        """Every Git repository backing *profile_id*."""
        stmt = self._base_select().where(ConfigurationGitRepository.profile_id == profile_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ConfigurationGitRepositoryRepository"]
