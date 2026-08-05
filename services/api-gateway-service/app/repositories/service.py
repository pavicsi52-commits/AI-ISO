"""The API service repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.service import ApiService


class ApiServiceRepository(BaseRepository[ApiService]):
    """The registered-backend-service catalogue."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ApiService, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, service_id: UUID) -> ApiService:
        """One service by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ApiService.organization_id == organization_id)
            .where(ApiService.id == service_id)
        )
        result = await self._session.execute(stmt)
        found: ApiService | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No service with id {service_id} in this organization.")
        return found

    async def get_by_name(self, organization_id: UUID, name: str) -> ApiService | None:
        """The service registered under *name*, if any."""
        stmt = (
            self._base_select()
            .where(ApiService.organization_id == organization_id)
            .where(ApiService.name == name)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_org(
        self, organization_id: UUID, *, enabled: bool | None = None
    ) -> list[ApiService]:
        """Services registered in this organization."""
        stmt = self._base_select().where(ApiService.organization_id == organization_id)
        if enabled is not None:
            stmt = stmt.where(ApiService.enabled.is_(enabled))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ApiServiceRepository"]
