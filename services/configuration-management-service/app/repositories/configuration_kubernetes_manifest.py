"""Repository for :class:`app.models.configuration_kubernetes_manifest
.ConfigurationKubernetesManifest`.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration_kubernetes_manifest import ConfigurationKubernetesManifest


class ConfigurationKubernetesManifestRepository(BaseRepository[ConfigurationKubernetesManifest]):
    """CRUD plus lookup for :class:`ConfigurationKubernetesManifest`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConfigurationKubernetesManifest, tenant_scope=tenant_scope)

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationKubernetesManifest]:
        """Every Kubernetes manifest backing *profile_id*."""
        stmt = self._base_select().where(ConfigurationKubernetesManifest.profile_id == profile_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ConfigurationKubernetesManifestRepository"]
