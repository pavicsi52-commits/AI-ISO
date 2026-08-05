"""The API key and API key permission repositories."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.apikey import ApiKey, ApiKeyPermission


class ApiKeyRepository(BaseRepository[ApiKey]):
    """Issued API keys."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ApiKey, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, api_key_id: UUID) -> ApiKey:
        """One key by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ApiKey.organization_id == organization_id)
            .where(ApiKey.id == api_key_id)
        )
        result = await self._session.execute(stmt)
        found: ApiKey | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No API key with id {api_key_id} in this organization.")
        return found

    async def get_by_key_id(self, key_id: str) -> ApiKey | None:
        """The key row for *key_id* (an opaque identifier, never the secret itself),
        unscoped by organization -- used for admin lookups, not authentication."""
        stmt = self._base_select().where(ApiKey.key_id == key_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_by_hashed_key(self, hashed_key: str) -> ApiKey | None:
        """The key row matching an already-hashed raw key, unscoped by organization.

        This is the only lookup a caller's own presented secret can
        drive: `shared_core.security.apikey`'s ``key_id`` is a separate,
        independently-generated identifier never derivable from the raw
        key or its hash, so authentication -- which only ever has the
        raw key a caller presented -- must look up by hash, not by id.
        """
        stmt = self._base_select().where(ApiKey.hashed_key == hashed_key)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_client(self, organization_id: UUID, client_id: UUID) -> list[ApiKey]:
        """Every key issued to one client."""
        stmt = (
            self._base_select()
            .where(ApiKey.organization_id == organization_id)
            .where(ApiKey.client_id == client_id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class ApiKeyPermissionRepository(BaseRepository[ApiKeyPermission]):
    """Fine-grained per-key permission grants."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ApiKeyPermission, tenant_scope=tenant_scope)

    async def list_for_key(self, organization_id: UUID, api_key_id: UUID) -> list[ApiKeyPermission]:
        """Every permission grant for one key."""
        stmt = (
            self._base_select()
            .where(ApiKeyPermission.organization_id == organization_id)
            .where(ApiKeyPermission.api_key_id == api_key_id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ApiKeyPermissionRepository", "ApiKeyRepository"]
