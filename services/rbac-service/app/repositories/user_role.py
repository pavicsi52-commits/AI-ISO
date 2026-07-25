"""Repository for :class:`app.models.user_role.UserRole`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_role import UserRole


class UserRoleRepository(BaseRepository[UserRole]):
    """CRUD plus lookup for :class:`UserRole` (system-scoped assignments)."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, UserRole, tenant_scope=tenant_scope)

    async def list_for_user(self, user_id: UUID) -> list[UserRole]:
        """Every system-scoped role assignment for *user_id*."""
        stmt = self._base_select().where(UserRole.user_id == user_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, user_id: UUID, role_id: UUID) -> UserRole | None:
        """Return *user_id*'s assignment of *role_id*, or ``None``."""
        stmt = self._base_select().where(UserRole.user_id == user_id, UserRole.role_id == role_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["UserRoleRepository"]
