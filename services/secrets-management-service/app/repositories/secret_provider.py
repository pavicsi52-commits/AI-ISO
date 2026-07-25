"""Repository for :class:`app.models.secret_provider.SecretProvider`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.secret_provider import SecretProvider


class SecretProviderRepository(BaseRepository[SecretProvider]):
    """CRUD plus lookup for :class:`SecretProvider`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, SecretProvider, tenant_scope=tenant_scope)

    async def get_by_name(self, organization_id: UUID, name: str) -> SecretProvider | None:
        """Return the provider identified by *name* within *organization_id*, or ``None``."""
        stmt = self._base_select().where(
            SecretProvider.organization_id == organization_id, SecretProvider.name == name
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_org(self, organization_id: UUID) -> list[SecretProvider]:
        """Every provider configured for *organization_id*."""
        stmt = self._base_select().where(SecretProvider.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["SecretProviderRepository"]
