"""Repository for :class:`app.models.session.Session`."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session


class SessionRepository(BaseRepository[Session]):
    """CRUD plus lookup/listing for :class:`Session`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, Session, tenant_scope=tenant_scope)

    async def get_by_session_id(self, session_id: str) -> Session | None:
        """Return the session row with the given ``session_id`` (the Redis-side key)."""
        stmt = self._base_select().where(Session.session_id == session_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active_for_user(self, user_id: UUID) -> list[Session]:
        """Every currently un-revoked session belonging to *user_id* ("GET /auth/sessions")."""
        stmt = self._base_select().where(Session.user_id == user_id, Session.revoked_at.is_(None))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def revoke_all_for_user(self, user_id: UUID, *, reason: str) -> int:
        """Mark every active session of *user_id* as revoked, returning how many were touched."""
        sessions = await self.list_active_for_user(user_id)
        now = datetime.now(UTC)
        for row in sessions:
            row.revoked_at = now
            row.revoked_reason = reason
        return len(sessions)


__all__ = ["SessionRepository"]
