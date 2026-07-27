"""Repository for :class:`app.models.playbook_audit.PlaybookAuditEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playbook_audit import PlaybookAuditEntry


class PlaybookAuditRepository(BaseRepository[PlaybookAuditEntry]):
    """CRUD plus lookup for :class:`PlaybookAuditEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PlaybookAuditEntry, tenant_scope=tenant_scope)

    async def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookAuditEntry]:
        """Every audit entry for *playbook_id*, newest first."""
        stmt = (
            self._base_select()
            .where(PlaybookAuditEntry.playbook_id == playbook_id)
            .order_by(desc(PlaybookAuditEntry.created_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["PlaybookAuditRepository"]
