"""Repository for :class:`app.models.configuration_ansible_inventory
.ConfigurationAnsibleInventory`.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration_ansible_inventory import ConfigurationAnsibleInventory


class ConfigurationAnsibleInventoryRepository(BaseRepository[ConfigurationAnsibleInventory]):
    """CRUD plus lookup for :class:`ConfigurationAnsibleInventory`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConfigurationAnsibleInventory, tenant_scope=tenant_scope)

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationAnsibleInventory]:
        """Every Ansible inventory bundle backing *profile_id*."""
        stmt = self._base_select().where(ConfigurationAnsibleInventory.profile_id == profile_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ConfigurationAnsibleInventoryRepository"]
