"""``connector_health`` repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.health import ConnectorHealth


class ConnectorHealthRepository(BaseRepository[ConnectorHealth]):
    """Automated connector health-probe results."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConnectorHealth, tenant_scope=tenant_scope)

    async def list_for_connector(
        self, connector_id: UUID, *, limit: int = 50
    ) -> list[ConnectorHealth]:
        """Recent health checks for one connector, newest first."""
        stmt = (
            self._base_select()
            .where(ConnectorHealth.connector_id == connector_id)
            .order_by(ConnectorHealth.checked_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def latest_for_connector(self, connector_id: UUID) -> ConnectorHealth | None:
        """The most recent health check for one connector, if any."""
        rows = await self.list_for_connector(connector_id, limit=1)
        return rows[0] if rows else None


__all__ = ["ConnectorHealthRepository"]
