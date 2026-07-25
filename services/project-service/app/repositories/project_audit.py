"""Repository for :class:`app.models.project_audit.ProjectAuditEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_audit import ProjectAuditEntry


class ProjectAuditRepository(BaseRepository[ProjectAuditEntry]):
    """CRUD plus listing for :class:`ProjectAuditEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ProjectAuditEntry, tenant_scope=tenant_scope)

    async def list_recent_for_project(
        self, project_id: UUID, *, limit: int = 50
    ) -> list[ProjectAuditEntry]:
        """The *limit* most recent audit entries for *project_id*, newest first."""
        stmt = (
            self._base_select()
            .where(ProjectAuditEntry.project_id == project_id)
            .order_by(desc(ProjectAuditEntry.created_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ProjectAuditRepository"]
