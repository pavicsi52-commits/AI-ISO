"""Repository for :class:`app.models.alert_deduplication.AlertDeduplication`."""

from __future__ import annotations

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_deduplication import AlertDeduplication


class AlertDeduplicationRepository(BaseRepository[AlertDeduplication]):
    """CRUD plus lookup for :class:`AlertDeduplication`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AlertDeduplication, tenant_scope=tenant_scope)

    async def get_by_fingerprint(self, fingerprint: str) -> AlertDeduplication | None:
        """Return the registry entry for *fingerprint*, if one exists.

        ``fingerprint`` is globally unique in the schema (it already
        encodes the organization), so no separate tenant filter is
        needed to keep two organizations' own entries apart.
        """
        stmt = self._base_select().where(AlertDeduplication.fingerprint == fingerprint)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["AlertDeduplicationRepository"]
