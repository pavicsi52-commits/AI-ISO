"""Repository for :class:`app.models.guardrail.AgentGuardrail`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import GuardrailType
from app.models.guardrail import AgentGuardrail


class AgentGuardrailRepository(BaseRepository[AgentGuardrail]):
    """CRUD plus lookup for :class:`AgentGuardrail`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AgentGuardrail, tenant_scope=tenant_scope)

    async def get_for_agent(
        self, organization_id: UUID, agent_id: UUID, guardrail_type: GuardrailType
    ) -> AgentGuardrail | None:
        """Return *agent_id*'s own override for *guardrail_type*, if any.

        Callers needing the effective config should try this first,
        then fall back to :meth:`get_org_default` -- an agent-specific
        row always wins over the organization's own default.
        """
        stmt = self._base_select().where(
            AgentGuardrail.organization_id == organization_id,
            AgentGuardrail.agent_id == agent_id,
            AgentGuardrail.guardrail_type == guardrail_type,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_org_default(
        self, organization_id: UUID, guardrail_type: GuardrailType
    ) -> AgentGuardrail | None:
        """Return *organization_id*'s own org-wide default for
        *guardrail_type* (``agent_id IS NULL``), if any."""
        stmt = self._base_select().where(
            AgentGuardrail.organization_id == organization_id,
            AgentGuardrail.agent_id.is_(None),
            AgentGuardrail.guardrail_type == guardrail_type,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_effective(self, organization_id: UUID, agent_id: UUID) -> list[AgentGuardrail]:
        """Every guardrail row that could apply to *agent_id* -- its
        own overrides plus every org-wide default. Resolving which one
        wins per type is the caller's own job (agent-specific first).
        """
        stmt = self._base_select().where(
            AgentGuardrail.organization_id == organization_id,
            or_(AgentGuardrail.agent_id == agent_id, AgentGuardrail.agent_id.is_(None)),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AgentGuardrailRepository"]
