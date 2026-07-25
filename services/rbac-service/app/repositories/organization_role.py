"""Repository for :class:`app.models.organization_role.OrganizationRole`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization_role import OrganizationRole


class OrganizationRoleRepository(BaseRepository[OrganizationRole]):
    """CRUD plus lookup for :class:`OrganizationRole`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, OrganizationRole, tenant_scope=tenant_scope)

    async def list_for_user(self, user_id: UUID) -> list[OrganizationRole]:
        """Every organization-scoped role assignment for *user_id*."""
        stmt = self._base_select().where(OrganizationRole.user_id == user_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(
        self, user_id: UUID, role_id: UUID, organization_id: UUID
    ) -> OrganizationRole | None:
        """Return *user_id*'s assignment of *role_id* within *organization_id*, or ``None``."""
        stmt = self._base_select().where(
            OrganizationRole.user_id == user_id,
            OrganizationRole.role_id == role_id,
            OrganizationRole.organization_id == organization_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["OrganizationRoleRepository"]
