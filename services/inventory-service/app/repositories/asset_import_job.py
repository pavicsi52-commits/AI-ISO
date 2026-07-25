"""Repository for :class:`app.models.asset_import_job.AssetImportJob`."""

from __future__ import annotations

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_import_job import AssetImportJob


class AssetImportJobRepository(BaseRepository[AssetImportJob]):
    """CRUD for :class:`AssetImportJob`. No lookups beyond the inherited
    ``get_by_id``/``require_by_id`` are needed: jobs are only ever
    addressed by their own id.
    """

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetImportJob, tenant_scope=tenant_scope)


__all__ = ["AssetImportJobRepository"]
