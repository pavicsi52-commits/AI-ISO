"""Repository for :class:`app.models.audit.AuthenticationAuditEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuthenticationAuditEntry


class AuthenticationAuditRepository(BaseRepository[AuthenticationAuditEntry]):
    """CRUD plus recent-history listing for :class:`AuthenticationAuditEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AuthenticationAuditEntry, tenant_scope=tenant_scope)

    async def list_recent_for_user(
        self, user_id: UUID, *, limit: int = 50
    ) -> list[AuthenticationAuditEntry]:
        """The *limit* most recent audit entries for *user_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AuthenticationAuditEntry.user_id == user_id)
            .order_by(desc(AuthenticationAuditEntry.created_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AuthenticationAuditRepository"]
