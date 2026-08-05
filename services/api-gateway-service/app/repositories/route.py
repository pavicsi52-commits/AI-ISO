"""The API route repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.route import ApiRoute


class ApiRouteRepository(BaseRepository[ApiRoute]):
    """The routing table."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ApiRoute, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, route_id: UUID) -> ApiRoute:
        """One route by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ApiRoute.organization_id == organization_id)
            .where(ApiRoute.id == route_id)
        )
        result = await self._session.execute(stmt)
        found: ApiRoute | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No route with id {route_id} in this organization.")
        return found

    async def list_for_org(
        self, organization_id: UUID, *, service_id: UUID | None = None, enabled: bool | None = None
    ) -> list[ApiRoute]:
        """Every route in this organization, ordered by priority."""
        stmt = self._base_select().where(ApiRoute.organization_id == organization_id)
        if service_id is not None:
            stmt = stmt.where(ApiRoute.service_id == service_id)
        if enabled is not None:
            stmt = stmt.where(ApiRoute.enabled.is_(enabled))
        stmt = stmt.order_by(ApiRoute.priority)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ApiRouteRepository"]
