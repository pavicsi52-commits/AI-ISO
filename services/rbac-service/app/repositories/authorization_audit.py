"""Repository for :class:`app.models.authorization_audit.AuthorizationAuditEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.authorization_audit import AuthorizationAuditEntry


class AuthorizationAuditRepository(BaseRepository[AuthorizationAuditEntry]):
    """CRUD plus listing for :class:`AuthorizationAuditEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AuthorizationAuditEntry, tenant_scope=tenant_scope)

    async def list_recent_for_user(
        self, user_id: UUID, *, limit: int = 50
    ) -> list[AuthorizationAuditEntry]:
        """The *limit* most recent audit entries for *user_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AuthorizationAuditEntry.user_id == user_id)
            .order_by(desc(AuthorizationAuditEntry.created_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AuthorizationAuditRepository"]
