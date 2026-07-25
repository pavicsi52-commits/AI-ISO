"""Repository for :class:`app.models.configuration_policy.ConfigurationPolicy`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration_policy import ConfigurationPolicy
from app.models.enums import PolicyType


class ConfigurationPolicyRepository(BaseRepository[ConfigurationPolicy]):
    """CRUD plus lookup for :class:`ConfigurationPolicy`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConfigurationPolicy, tenant_scope=tenant_scope)

    async def list_for_org(
        self, organization_id: UUID, *, policy_type: PolicyType | None = None
    ) -> list[ConfigurationPolicy]:
        """Every policy belonging to *organization_id*, optionally narrowed
        to a single *policy_type*.
        """
        stmt = self._base_select().where(ConfigurationPolicy.organization_id == organization_id)
        if policy_type is not None:
            stmt = stmt.where(ConfigurationPolicy.policy_type == policy_type)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ConfigurationPolicyRepository"]
