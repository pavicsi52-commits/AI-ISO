"""Repository for :class:`app.models.project_member.ProjectMember`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_member import ProjectMember


class ProjectMemberRepository(BaseRepository[ProjectMember]):
    """CRUD plus lookup for :class:`ProjectMember`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ProjectMember, tenant_scope=tenant_scope)

    async def get(self, project_id: UUID, user_id: UUID) -> ProjectMember | None:
        """Return *user_id*'s membership in *project_id*, or ``None``."""
        stmt = self._base_select().where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_project(self, project_id: UUID) -> list[ProjectMember]:
        """Every member of *project_id*."""
        stmt = self._base_select().where(ProjectMember.project_id == project_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_user(self, user_id: UUID) -> list[ProjectMember]:
        """Every project *user_id* belongs to."""
        stmt = self._base_select().where(ProjectMember.user_id == user_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_project(self, project_id: UUID) -> int:
        """The number of members in *project_id*."""
        return await self.count(project_id=project_id)


__all__ = ["ProjectMemberRepository"]
