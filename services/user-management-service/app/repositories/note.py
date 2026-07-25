"""Repository for :class:`app.models.note.UserNote`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import UserNote


class UserNoteRepository(BaseRepository[UserNote]):
    """CRUD plus listing for :class:`UserNote`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, UserNote, tenant_scope=tenant_scope)

    async def list_for_user(self, user_id: UUID) -> list[UserNote]:
        """Every note on record for *user_id*, newest first."""
        stmt = (
            self._base_select()
            .where(UserNote.user_id == user_id)
            .order_by(desc(UserNote.created_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["UserNoteRepository"]
