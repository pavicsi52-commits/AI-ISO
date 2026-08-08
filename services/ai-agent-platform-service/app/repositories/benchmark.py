"""Repository for :class:`app.models.benchmark.AgentBenchmark`."""

from __future__ import annotations

from datetime import datetime
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

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 200, offset: int = 0
    ) -> list[AgentBenchmark]:
        """Every benchmark run in *organization_id*, newest first --
        backs ``GET /agents/benchmarks``."""
        stmt = (
            self._base_select()
            .where(AgentBenchmark.organization_id == organization_id)
            .order_by(AgentBenchmark.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_agent_ids_benchmarked_since(
        self, organization_id: UUID, *, since: datetime
    ) -> set[UUID]:
        """Every agent id with at least one benchmark run started at or
        after *since* -- backs the benchmark sweep's own "does this
        agent still need a health-check benchmark" decision."""
        stmt = self._base_select().where(
            AgentBenchmark.organization_id == organization_id,
            AgentBenchmark.started_at >= since,
        )
        result = await self._session.execute(stmt)
        return {row.agent_id for row in result.scalars().all()}


__all__ = ["AgentBenchmarkRepository"]
