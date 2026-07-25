"""Repository for :class:`app.models.discovery_credential.DiscoveryCredential`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_credential import DiscoveryCredential


class DiscoveryCredentialRepository(BaseRepository[DiscoveryCredential]):
    """CRUD plus lookup for :class:`DiscoveryCredential`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DiscoveryCredential, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[DiscoveryCredential]:
        """Every credential reference defined for *organization_id*."""
        stmt = self._base_select().where(DiscoveryCredential.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name(self, organization_id: UUID, name: str) -> DiscoveryCredential | None:
        """Return the credential reference identified by *name* within
        *organization_id*, or ``None``.
        """
        stmt = self._base_select().where(
            DiscoveryCredential.organization_id == organization_id,
            DiscoveryCredential.name == name,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["DiscoveryCredentialRepository"]
