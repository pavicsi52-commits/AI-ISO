"""``connector_events`` repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import ConnectorEvent


class ConnectorEventRepository(BaseRepository[ConnectorEvent]):
    """Events raised through, or by, a connector."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConnectorEvent, tenant_scope=tenant_scope)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        connector_id: UUID | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ConnectorEvent]:
        """Events in this organization, newest first."""
        stmt = self._base_select().where(ConnectorEvent.organization_id == organization_id)
        if connector_id is not None:
            stmt = stmt.where(ConnectorEvent.connector_id == connector_id)
        stmt = stmt.order_by(ConnectorEvent.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ConnectorEventRepository"]
