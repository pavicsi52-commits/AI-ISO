"""Repository for :class:`app.models.discovery_rule.DiscoveryRule`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_rule import DiscoveryRule


class DiscoveryRuleRepository(BaseRepository[DiscoveryRule]):
    """CRUD plus lookup for :class:`DiscoveryRule`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DiscoveryRule, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[DiscoveryRule]:
        """Every active rule defined for *organization_id*."""
        stmt = self._base_select().where(
            DiscoveryRule.organization_id == organization_id, DiscoveryRule.is_active.is_(True)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_profile(self, profile_id: UUID) -> list[DiscoveryRule]:
        """Every active rule associated with *profile_id*, highest priority first."""
        stmt = (
            self._base_select()
            .where(DiscoveryRule.profile_id == profile_id, DiscoveryRule.is_active.is_(True))
            .order_by(DiscoveryRule.priority.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["DiscoveryRuleRepository"]
