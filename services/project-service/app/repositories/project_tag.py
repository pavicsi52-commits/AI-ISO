"""Repository for :class:`app.models.project_tag.ProjectTag`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_tag import ProjectTag


class ProjectTagRepository(BaseRepository[ProjectTag]):
    """CRUD plus lookup for :class:`ProjectTag`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ProjectTag, tenant_scope=tenant_scope)

    async def get_by_label(self, project_id: UUID, label: str) -> ProjectTag | None:
        """Return the tag identified by *label* on *project_id*, or ``None``."""
        stmt = self._base_select().where(
            ProjectTag.project_id == project_id, ProjectTag.label == label
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_project(self, project_id: UUID) -> list[ProjectTag]:
        """Every tag assigned to *project_id*."""
        stmt = self._base_select().where(ProjectTag.project_id == project_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_project_ids_for_labels(
        self, organization_id: UUID, labels: list[str]
    ) -> set[UUID]:
        """Every distinct ``project_id`` in *organization_id* carrying at
        least one tag whose label is in *labels* ("EXPORT": "Filtered Export").
        """
        stmt = self._base_select().where(
            ProjectTag.organization_id == organization_id, ProjectTag.label.in_(labels)
        )
        result = await self._session.execute(stmt)
        return {tag.project_id for tag in result.scalars().all()}


__all__ = ["ProjectTagRepository"]
