"""Repository for :class:`app.models.import_job.UserImportJob`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.import_job import UserImportJob


class UserImportJobRepository(BaseRepository[UserImportJob]):
    """CRUD plus per-requester listing for :class:`UserImportJob`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, UserImportJob, tenant_scope=tenant_scope)

    async def list_for_requester(
        self, requested_by: UUID, *, limit: int = 20
    ) -> list[UserImportJob]:
        """The *limit* most recent import jobs *requested_by* submitted, newest first."""
        stmt = (
            self._base_select()
            .where(UserImportJob.requested_by == requested_by)
            .order_by(desc(UserImportJob.created_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["UserImportJobRepository"]
