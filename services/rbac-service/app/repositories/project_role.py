"""Repository for :class:`app.models.project_role.ProjectRole`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_role import ProjectRole


class ProjectRoleRepository(BaseRepository[ProjectRole]):
    """CRUD plus lookup for :class:`ProjectRole`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ProjectRole, tenant_scope=tenant_scope)

    async def list_for_user(self, user_id: UUID) -> list[ProjectRole]:
        """Every project-scoped role assignment for *user_id*."""
        stmt = self._base_select().where(ProjectRole.user_id == user_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, user_id: UUID, role_id: UUID, project_id: UUID) -> ProjectRole | None:
        """Return *user_id*'s assignment of *role_id* within *project_id*, or ``None``."""
        stmt = self._base_select().where(
            ProjectRole.user_id == user_id,
            ProjectRole.role_id == role_id,
            ProjectRole.project_id == project_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["ProjectRoleRepository"]
