"""Repository for :class:`app.models.report_recipient.ReportRecipient`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_recipient import ReportRecipient


class ReportRecipientRepository(BaseRepository[ReportRecipient]):
    """CRUD plus lookups for :class:`ReportRecipient`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ReportRecipient, tenant_scope=tenant_scope)

    async def list_for_job(
        self, job_id: UUID, *, enabled_only: bool = False
    ) -> list[ReportRecipient]:
        """Standing recipients of one report."""
        stmt = self._base_select().where(ReportRecipient.job_id == job_id)
        if enabled_only:
            stmt = stmt.where(ReportRecipient.enabled.is_(True))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ReportRecipientRepository"]
