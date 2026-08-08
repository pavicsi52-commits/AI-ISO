"""Repository for :class:`app.models.evaluation.AgentEvaluation`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evaluation import AgentEvaluation


class AgentEvaluationRepository(BaseRepository[AgentEvaluation]):
    """CRUD plus lookup for :class:`AgentEvaluation`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AgentEvaluation, tenant_scope=tenant_scope)

    async def list_for_agent(self, agent_id: UUID) -> list[AgentEvaluation]:
        """Every evaluation recorded for *agent_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AgentEvaluation.agent_id == agent_id)
            .order_by(AgentEvaluation.evaluated_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_execution(self, execution_id: UUID) -> list[AgentEvaluation]:
        """Every evaluation recorded against one specific execution."""
        stmt = self._base_select().where(AgentEvaluation.execution_id == execution_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 200, offset: int = 0
    ) -> list[AgentEvaluation]:
        """Every evaluation in *organization_id*, newest first -- backs
        ``GET /agents/evaluations``."""
        stmt = (
            self._base_select()
            .where(AgentEvaluation.organization_id == organization_id)
            .order_by(AgentEvaluation.evaluated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AgentEvaluationRepository"]
