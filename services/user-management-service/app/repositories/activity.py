"""Repository for :class:`app.models.activity.UserActivityEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import UserActivityEntry


class UserActivityRepository(BaseRepository[UserActivityEntry]):
    """CRUD plus recent-activity listing for :class:`UserActivityEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, UserActivityEntry, tenant_scope=tenant_scope)

    async def list_recent_for_user(
        self, user_id: UUID, *, limit: int = 50
    ) -> list[UserActivityEntry]:
        """The *limit* most recent activity entries for *user_id*, newest first."""
        stmt = (
            self._base_select()
            .where(UserActivityEntry.user_id == user_id)
            .order_by(desc(UserActivityEntry.created_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["UserActivityRepository"]
