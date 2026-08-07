"""Repository for :class:`app.models.benchmark.AgentBenchmark`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.benchmark import AgentBenchmark


class AgentBenchmarkRepository(BaseRepository[AgentBenchmark]):
    """CRUD plus lookup for :class:`AgentBenchmark`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AgentBenchmark, tenant_scope=tenant_scope)

    async def list_for_agent(self, agent_id: UUID) -> list[AgentBenchmark]:
        """Every benchmark run recorded for *agent_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AgentBenchmark.agent_id == agent_id)
            .order_by(AgentBenchmark.started_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AgentBenchmarkRepository"]
