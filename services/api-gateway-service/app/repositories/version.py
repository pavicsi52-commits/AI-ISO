"""The API version repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.version import ApiVersion


class ApiVersionRepository(BaseRepository[ApiVersion]):
    """Every version a registered service exposes."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ApiVersion, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, version_id: UUID) -> ApiVersion:
        """One version by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ApiVersion.organization_id == organization_id)
            .where(ApiVersion.id == version_id)
        )
        result = await self._session.execute(stmt)
        found: ApiVersion | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No version with id {version_id} in this organization.")
        return found

    async def list_for_service(self, organization_id: UUID, service_id: UUID) -> list[ApiVersion]:
        """Every version registered for one service."""
        stmt = (
            self._base_select()
            .where(ApiVersion.organization_id == organization_id)
            .where(ApiVersion.service_id == service_id)
            .order_by(ApiVersion.version_label)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_default(self, organization_id: UUID, service_id: UUID) -> ApiVersion | None:
        """The version currently marked default for one service, if any."""
        stmt = (
            self._base_select()
            .where(ApiVersion.organization_id == organization_id)
            .where(ApiVersion.service_id == service_id)
            .where(ApiVersion.is_default.is_(True))
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["ApiVersionRepository"]
