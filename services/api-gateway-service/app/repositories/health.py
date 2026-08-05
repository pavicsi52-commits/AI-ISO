"""The API service health repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.health import ApiServiceHealth


class ApiServiceHealthRepository(BaseRepository[ApiServiceHealth]):
    """Every backend instance's own last-probed health and circuit state."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ApiServiceHealth, tenant_scope=tenant_scope)

    async def get_for_instance(
        self, organization_id: UUID, service_id: UUID, instance_url: str
    ) -> ApiServiceHealth | None:
        """The health row for one exact instance, if it has ever been probed."""
        stmt = (
            self._base_select()
            .where(ApiServiceHealth.organization_id == organization_id)
            .where(ApiServiceHealth.service_id == service_id)
            .where(ApiServiceHealth.instance_url == instance_url)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_service(
        self, organization_id: UUID, service_id: UUID
    ) -> list[ApiServiceHealth]:
        """Every instance's own latest health for one service."""
        stmt = (
            self._base_select()
            .where(ApiServiceHealth.organization_id == organization_id)
            .where(ApiServiceHealth.service_id == service_id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_org(self, organization_id: UUID) -> list[ApiServiceHealth]:
        """Every probed instance across every service in this organization."""
        stmt = self._base_select().where(ApiServiceHealth.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ApiServiceHealthRepository"]
