"""Repository for :class:`app.models.project_export_job.ProjectExportJob`."""

from __future__ import annotations

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_export_job import ProjectExportJob


class ProjectExportJobRepository(BaseRepository[ProjectExportJob]):
    """CRUD for :class:`ProjectExportJob`. No lookups beyond the inherited
    ``get_by_id``/``require_by_id`` are needed: jobs are only ever
    addressed by their own id.
    """

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ProjectExportJob, tenant_scope=tenant_scope)


__all__ = ["ProjectExportJobRepository"]
