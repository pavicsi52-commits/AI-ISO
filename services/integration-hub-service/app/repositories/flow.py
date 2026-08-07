"""``connector_flows`` repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flow import ConnectorFlow


class ConnectorFlowRepository(BaseRepository[ConnectorFlow]):
    """Integration flow definitions."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConnectorFlow, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, flow_id: UUID) -> ConnectorFlow:
        """One flow by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ConnectorFlow.organization_id == organization_id)
            .where(ConnectorFlow.id == flow_id)
        )
        result = await self._session.execute(stmt)
        found: ConnectorFlow | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No flow with id {flow_id} in this organization.")
        return found

    async def list_for_org(
        self, organization_id: UUID, *, enabled: bool | None = None
    ) -> list[ConnectorFlow]:
        """Flows in this organization, newest first."""
        stmt = self._base_select().where(ConnectorFlow.organization_id == organization_id)
        if enabled is not None:
            stmt = stmt.where(ConnectorFlow.enabled.is_(enabled))
        stmt = stmt.order_by(ConnectorFlow.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_due_for_schedule(self, *, limit: int = 200) -> list[ConnectorFlow]:
        """Every enabled, schedule-triggered flow -- the flow scheduler sweep decides due-ness
        against ``last_run_at``/``schedule_interval_seconds`` itself, this only narrows the set."""
        stmt = (
            self._base_select()
            .where(ConnectorFlow.enabled.is_(True))
            .where(ConnectorFlow.trigger == "scheduled")
            .where(ConnectorFlow.schedule_interval_seconds.is_not(None))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ConnectorFlowRepository"]
