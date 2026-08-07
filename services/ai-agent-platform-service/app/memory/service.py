"""Agent memory (docs/060 "MEMORY").

Mirrors ``ai-assistant-service``'s own ``app/memory/service.py``
(Prompt 046) ``MemoryService`` shape -- resolve most-specific-scope-
first, dedup by key, render as system context, remember/forget -- but
adapted to this service's own :class:`~app.models.memory.AgentMemory`
schema, which has no separate conversation-thread entity: every scoped
memory is keyed off an *agent* rather than an organization, and its
scopes are docs/060's own six memory kinds rather than ai-assistant
-service's five tenant-breadth scopes.

**Scope precedence and reference resolution**
(most specific first, matching :class:`~app.models.memory.AgentMemory`'s
own docstring):

1. ``TASK`` -- keyed by ``task_id``. Scratch memory for one task run.
2. ``CONVERSATION`` -- keyed by ``session_id``. The current exchange
   within a session; typically short-lived (a caller-set
   ``expires_at``).
3. ``SESSION`` -- also keyed by ``session_id``. Broader than
   ``CONVERSATION`` (no separate conversation-thread entity exists in
   this schema, so both scopes resolve against the same session
   reference; ``CONVERSATION``'s own row wins on a shared key since it
   is checked first).
4. ``SHORT_TERM`` -- agent-wide, no reference; expected to carry its
   own ``expires_at``.
5. ``LONG_TERM`` -- agent-wide, no reference, no expiry.
6. ``KNOWLEDGE_REFERENCE`` -- agent-wide; a pointer into an external
   knowledge source (e.g. a Knowledge Graph node ID) rather than an
   inline fact.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.enums import MemoryScope
from app.models.memory import AgentMemory
from app.repositories.memory import AgentMemoryRepository

_SCOPE_PRECEDENCE: tuple[MemoryScope, ...] = (
    MemoryScope.TASK,
    MemoryScope.CONVERSATION,
    MemoryScope.SESSION,
    MemoryScope.SHORT_TERM,
    MemoryScope.LONG_TERM,
    MemoryScope.KNOWLEDGE_REFERENCE,
)
"""Most specific first. A task-level fact wins over a broader one
carrying the same key.
"""

_REFERENCE_SCOPES = (MemoryScope.CONVERSATION, MemoryScope.SESSION)
"""Scopes resolved against ``session_id`` rather than ``task_id`` or no
reference at all."""


class MemoryService:
    """Resolves live memory into context and manages durable facts for
    one agent."""

    def __init__(self, memories: AgentMemoryRepository) -> None:
        self._memories = memories

    async def resolve_memories(
        self,
        agent_id: UUID,
        *,
        session_id: UUID | None = None,
        task_id: UUID | None = None,
        moment: datetime | None = None,
    ) -> list[AgentMemory]:
        """Every live memory applying to one agent run, most specific
        scope first.

        Deduplicated by key: only the most specific scope's own value
        for a given key survives.
        """
        now = moment or datetime.now(UTC)

        resolved: list[AgentMemory] = []
        seen_keys: set[str] = set()
        for scope in _SCOPE_PRECEDENCE:
            if scope is MemoryScope.TASK and task_id is None:
                continue
            if scope in _REFERENCE_SCOPES and session_id is None:
                continue

            rows = await self._memories.list_live(
                agent_id,
                scope,
                now,
                session_id=session_id if scope in _REFERENCE_SCOPES else None,
                task_id=task_id if scope is MemoryScope.TASK else None,
            )
            for memory in rows:
                if memory.key in seen_keys:
                    continue
                seen_keys.add(memory.key)
                resolved.append(memory)
        return resolved

    async def as_system_context(
        self,
        agent_id: UUID,
        *,
        session_id: UUID | None = None,
        task_id: UUID | None = None,
    ) -> str:
        """Render live memories as a system-context block, or ``""``.

        An empty string when nothing is remembered, so the caller can
        skip adding an empty system turn rather than sending the model
        a heading with nothing under it.
        """
        memories = await self.resolve_memories(agent_id, session_id=session_id, task_id=task_id)
        if not memories:
            return ""
        lines = [f"- {memory.key}: {memory.summary or memory.content}" for memory in memories]
        return "Remembered context for this agent:\n" + "\n".join(lines)

    async def remember(
        self,
        *,
        agent_id: UUID,
        organization_id: UUID,
        project_id: UUID | None,
        scope: MemoryScope,
        key: str,
        content: dict[str, object],
        summary: str | None = None,
        session_id: UUID | None = None,
        task_id: UUID | None = None,
        expires_at: datetime | None = None,
    ) -> AgentMemory:
        """Store or update one remembered fact.

        Updates in place when the key already exists in that scope
        (and reference, for ``TASK``/``CONVERSATION``/``SESSION``) --
        remembering "current plan" twice should correct the fact, not
        accumulate two contradictory ones. This is a service-level
        check, not a database constraint -- see
        :class:`~app.models.memory.AgentMemory`'s own docstring for why
        a DB-level uniqueness on these columns would be wrong here.
        """
        reference_session_id = session_id if scope in _REFERENCE_SCOPES else None
        reference_task_id = task_id if scope is MemoryScope.TASK else None

        existing = await self._memories.get_by_key(
            agent_id, scope, key, session_id=reference_session_id, task_id=reference_task_id
        )
        if existing is not None:
            existing.content = content
            existing.summary = summary
            existing.expires_at = expires_at
            return await self._memories.update(existing)

        return await self._memories.create(
            AgentMemory(
                organization_id=organization_id,
                project_id=project_id,
                agent_id=agent_id,
                scope=scope,
                key=key,
                content=content,
                summary=summary,
                session_id=reference_session_id,
                task_id=reference_task_id,
                expires_at=expires_at,
            )
        )

    async def search(
        self, agent_id: UUID, query: str, *, scope: MemoryScope | None = None
    ) -> list[AgentMemory]:
        """ "Memory Search" -- every live memory for *agent_id* whose own
        key or summary matches *query*, most recently created first is
        the repository's own default ordering.
        """
        return await self._memories.search_for_agent(agent_id, query, scope=scope)

    async def forget_expired(self, agent_id: UUID) -> int:
        """Purge expired memories for one agent, returning how many
        were removed."""
        return await self._memories.delete_expired(agent_id, datetime.now(UTC))


__all__ = ["MemoryService"]
