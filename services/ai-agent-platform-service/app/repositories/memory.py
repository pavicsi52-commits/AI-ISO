"""Repository for :class:`app.models.memory.AgentMemory`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.search import apply_search
from shared_core.database.tenant import TenantScope
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryScope
from app.models.memory import AgentMemory


class AgentMemoryRepository(BaseRepository[AgentMemory]):
    """CRUD plus lookup for :class:`AgentMemory`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AgentMemory, tenant_scope=tenant_scope)

    async def list_live(
        self,
        agent_id: UUID,
        scope: MemoryScope,
        moment: datetime,
        *,
        session_id: UUID | None = None,
        task_id: UUID | None = None,
    ) -> list[AgentMemory]:
        """Every unexpired memory in one scope for one agent
        ("Memory Expiration" -- enforced here, not by a cleanup job: an
        expired memory must stop influencing an agent's own context the
        moment it expires, not whenever a sweep next happens to run).

        *session_id*/*task_id* narrow further for the reference-scoped
        kinds (``SESSION``/``CONVERSATION`` use ``session_id``, ``TASK``
        uses ``task_id``); omit both for the agent-wide scopes
        (``SHORT_TERM``/``LONG_TERM``/``KNOWLEDGE_REFERENCE``).
        """
        stmt = self._base_select().where(
            AgentMemory.agent_id == agent_id,
            AgentMemory.scope == scope,
            or_(AgentMemory.expires_at.is_(None), AgentMemory.expires_at > moment),
        )
        if session_id is not None:
            stmt = stmt.where(AgentMemory.session_id == session_id)
        if task_id is not None:
            stmt = stmt.where(AgentMemory.task_id == task_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_agent(self, agent_id: UUID) -> list[AgentMemory]:
        """Every memory for *agent_id*, expired ones included.

        Deliberately unfiltered, unlike :meth:`list_live`: this backs
        the administrative memory listing, where seeing an expired-but-
        not-yet-purged row is the point. Context assembly must use
        :meth:`list_live` instead.
        """
        stmt = self._base_select().where(AgentMemory.agent_id == agent_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_key(
        self,
        agent_id: UUID,
        scope: MemoryScope,
        key: str,
        *,
        session_id: UUID | None = None,
        task_id: UUID | None = None,
    ) -> AgentMemory | None:
        """Return one remembered fact by key, if present.

        The natural key is ``(agent_id, scope, key)`` plus whichever
        reference the scope actually uses -- matching exactly what
        :meth:`list_live` filters by, so a fact resolved into context
        is always the same row :meth:`~app.services.memory.MemoryService
        .remember` would update.
        """
        stmt = self._base_select().where(
            AgentMemory.agent_id == agent_id,
            AgentMemory.scope == scope,
            AgentMemory.key == key,
        )
        if session_id is not None:
            stmt = stmt.where(AgentMemory.session_id == session_id)
        if task_id is not None:
            stmt = stmt.where(AgentMemory.task_id == task_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def search_for_agent(
        self, agent_id: UUID, query: str, *, scope: MemoryScope | None = None
    ) -> list[AgentMemory]:
        """ "Memory Search" -- every live memory for *agent_id* whose own
        ``key`` or ``summary`` matches *query*.
        """
        base_stmt = self._base_select().where(AgentMemory.agent_id == agent_id)
        if scope is not None:
            base_stmt = base_stmt.where(AgentMemory.scope == scope)
        stmt = apply_search(base_stmt, AgentMemory, ["key", "summary"], query)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_expired(self, agent_id: UUID, moment: datetime) -> int:
        """Purge *agent_id*'s own memories whose expiry has passed,
        returning how many were removed."""
        stmt = self._base_select().where(
            AgentMemory.agent_id == agent_id,
            AgentMemory.expires_at.is_not(None),
            AgentMemory.expires_at <= moment,
        )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        for row in rows:
            await self._session.delete(row)
        await self._session.flush()
        return len(rows)


__all__ = ["AgentMemoryRepository"]
