"""Repository for :class:`app.models.ai_audit.AiAuditEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_audit import AiAuditEntry


class AiAuditEntryRepository(BaseRepository[AiAuditEntry]):
    """CRUD plus lookup for :class:`AiAuditEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AiAuditEntry, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[AiAuditEntry]:
        """Every row belonging to *organization_id*."""
        stmt = self._base_select().where(AiAuditEntry.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AiAuditEntryRepository"]
