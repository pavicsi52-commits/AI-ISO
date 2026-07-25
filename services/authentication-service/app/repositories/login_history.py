"""Repository for :class:`app.models.login_history.LoginHistoryEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.login_history import LoginHistoryEntry


class LoginHistoryRepository(BaseRepository[LoginHistoryEntry]):
    """CRUD plus recent-history listing for :class:`LoginHistoryEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, LoginHistoryEntry, tenant_scope=tenant_scope)

    async def list_recent_for_user(
        self, user_id: UUID, *, limit: int = 20
    ) -> list[LoginHistoryEntry]:
        """The *limit* most recent logins for *user_id*, newest first."""
        stmt = (
            self._base_select()
            .where(LoginHistoryEntry.user_id == user_id)
            .order_by(desc(LoginHistoryEntry.created_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["LoginHistoryRepository"]
