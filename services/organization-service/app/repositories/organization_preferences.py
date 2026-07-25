"""Repository for :class:`app.models.organization_preferences.OrganizationPreferences`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization_preferences import OrganizationPreferences


class OrganizationPreferencesRepository(BaseRepository[OrganizationPreferences]):
    """CRUD plus lookup for :class:`OrganizationPreferences`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, OrganizationPreferences, tenant_scope=tenant_scope)

    async def get_for_org(self, organization_id: UUID) -> OrganizationPreferences | None:
        """Return *organization_id*'s preferences row, or ``None``."""
        stmt = self._base_select().where(OrganizationPreferences.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["OrganizationPreferencesRepository"]
