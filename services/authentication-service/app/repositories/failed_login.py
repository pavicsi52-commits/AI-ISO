"""Repository for :class:`app.models.failed_login.FailedLoginEntry`."""

from __future__ import annotations

from datetime import datetime

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.failed_login import FailedLoginEntry


class FailedLoginRepository(BaseRepository[FailedLoginEntry]):
    """CRUD plus recent-attempt counting for :class:`FailedLoginEntry` ("Account Security")."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, FailedLoginEntry, tenant_scope=tenant_scope)

    async def count_recent_for_identifier(self, identifier: str, *, since: datetime) -> int:
        """How many failed attempts *identifier* has made since *since*.

        Covers "Failed Login Tracking".
        """
        stmt = select(func.count()).where(
            FailedLoginEntry.identifier == identifier, FailedLoginEntry.created_at >= since
        )
        result = await self._session.execute(stmt.select_from(FailedLoginEntry))
        return int(result.scalar_one())


__all__ = ["FailedLoginRepository"]
