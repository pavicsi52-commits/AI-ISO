"""Repository for :class:`app.models.project_role.ProjectRole`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_role import ProjectRole


class ProjectRoleRepository(BaseRepository[ProjectRole]):
    """CRUD plus lookup for :class:`ProjectRole`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ProjectRole, tenant_scope=tenant_scope)

    async def get_by_code(self, project_id: UUID, code: str) -> ProjectRole | None:
        """Return the role identified by *code*, visible to *project_id*
        (a system role, or that project's own custom role), or ``None``.
        """
        stmt = self._base_select().where(
            ProjectRole.code == code,
            or_(ProjectRole.project_id.is_(None), ProjectRole.project_id == project_id),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_available_for_project(self, project_id: UUID) -> list[ProjectRole]:
        """Every role visible to *project_id*: every system role, plus that
        project's own custom roles.
        """
        stmt = self._base_select().where(
            or_(ProjectRole.project_id.is_(None), ProjectRole.project_id == project_id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ProjectRoleRepository"]
