"""Repository for :class:`app.models.project_note.ProjectNote`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_note import ProjectNote


class ProjectNoteRepository(BaseRepository[ProjectNote]):
    """CRUD plus lookup for :class:`ProjectNote`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ProjectNote, tenant_scope=tenant_scope)

    async def list_for_project(self, project_id: UUID) -> list[ProjectNote]:
        """Every note on *project_id*, pinned first, then newest first."""
        stmt = (
            self._base_select()
            .where(ProjectNote.project_id == project_id)
            .order_by(desc(ProjectNote.is_pinned), desc(ProjectNote.created_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ProjectNoteRepository"]
