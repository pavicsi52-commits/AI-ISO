"""Repository for :class:`app.models.key_rotation_history.KeyRotationHistoryEntry`."""

from __future__ import annotations

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.key_rotation_history import KeyRotationHistoryEntry


class KeyRotationHistoryRepository(BaseRepository[KeyRotationHistoryEntry]):
    """CRUD plus lookup for :class:`KeyRotationHistoryEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, KeyRotationHistoryEntry, tenant_scope=tenant_scope)

    async def list_all(self) -> list[KeyRotationHistoryEntry]:
        """Every encryption-key rotation event ever recorded, newest first."""
        stmt = self._base_select().order_by(desc(KeyRotationHistoryEntry.rotated_at))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["KeyRotationHistoryRepository"]
