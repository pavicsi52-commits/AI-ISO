"""Repository for :class:`app.models.project_import_job.ProjectImportJob`."""

from __future__ import annotations

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_import_job import ProjectImportJob


class ProjectImportJobRepository(BaseRepository[ProjectImportJob]):
    """CRUD for :class:`ProjectImportJob`. No lookups beyond the inherited
    ``get_by_id``/``require_by_id`` are needed: jobs are only ever
    addressed by their own id.
    """

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ProjectImportJob, tenant_scope=tenant_scope)


__all__ = ["ProjectImportJobRepository"]
