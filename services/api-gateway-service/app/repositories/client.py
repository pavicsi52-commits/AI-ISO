"""The API client repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import ApiClient


class ApiClientRepository(BaseRepository[ApiClient]):
    """The registered-caller catalogue."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ApiClient, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, client_id: UUID) -> ApiClient:
        """One client by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ApiClient.organization_id == organization_id)
            .where(ApiClient.id == client_id)
        )
        result = await self._session.execute(stmt)
        found: ApiClient | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No client with id {client_id} in this organization.")
        return found

    async def list_for_org(self, organization_id: UUID) -> list[ApiClient]:
        """Every client registered in this organization."""
        stmt = self._base_select().where(ApiClient.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ApiClientRepository"]
