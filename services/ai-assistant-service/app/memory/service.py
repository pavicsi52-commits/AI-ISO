"""Conversation and durable memory ("MEMORY").

Two distinct things share the name "memory" and are kept separate here
because they behave differently:

- **Conversation memory** is the recent turn history replayed into the
  model's own context. It is bounded by turn count ("Context
  Compression") -- an unbounded history would eventually exceed every
  model's window and cost more on every request.
- **Durable memory** (:class:`~app.models.ai_memory.AiMemory`) is
  remembered *facts* that outlive a thread, scoped to a conversation,
  session, user, organization, or project, each with its own optional
  expiry.

Scopes are resolved most-specific-first and deduplicated by key, so a
conversation-level fact overrides an organization-level one with the
same key rather than both being injected and contradicting each other.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.clients.base import ChatMessage
from app.models.ai_memory import AiMemory
from app.models.ai_message import AiMessage
from app.models.enums import MemoryScope, MessageRole
from app.repositories.ai_memory import AiMemoryRepository
from app.repositories.ai_message import AiMessageRepository

_SCOPE_PRECEDENCE: tuple[MemoryScope, ...] = (
    MemoryScope.CONVERSATION,
    MemoryScope.SESSION,
    MemoryScope.USER,
    MemoryScope.PROJECT,
    MemoryScope.ORGANIZATION,
)
"""Most specific first. A conversation-level fact wins over a broader
one carrying the same key.
"""


class MemoryService:
    """Assembles conversation context and manages durable memory."""

    def __init__(
        self,
        memories: AiMemoryRepository,
        messages: AiMessageRepository,
        *,
        conversation_turns: int,
    ) -> None:
        self._memories = memories
        self._messages = messages
        self._conversation_turns = conversation_turns

    async def conversation_history(self, conversation_id: UUID) -> list[ChatMessage]:
        """The recent turns of a conversation, oldest first.

        Tool-role turns are included: dropping them would leave the
        model seeing its own request for a tool with no answer, which
        reliably makes it request the same tool again.
        """
        rows = await self._messages.list_recent_for_conversation(
            conversation_id, limit=self._conversation_turns
        )
        return [
            ChatMessage(
                role=row.role if isinstance(row.role, MessageRole) else MessageRole(row.role),
                content=row.content,
            )
            for row in rows
        ]

    async def resolve_memories(
        self,
        organization_id: UUID,
        *,
        conversation_id: UUID | None = None,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        project_id: UUID | None = None,
        moment: datetime | None = None,
    ) -> list[AiMemory]:
        """Every live memory applying here, most specific scope first.

        Deduplicated by key: only the most specific scope's own value
        for a given key survives.
        """
        now = moment or datetime.now(UTC)
        references: dict[MemoryScope, str | None] = {
            MemoryScope.CONVERSATION: str(conversation_id) if conversation_id else None,
            MemoryScope.SESSION: str(session_id) if session_id else None,
            MemoryScope.USER: str(user_id) if user_id else None,
            MemoryScope.PROJECT: str(project_id) if project_id else None,
            MemoryScope.ORGANIZATION: str(organization_id),
        }

        resolved: list[AiMemory] = []
        seen_keys: set[str] = set()
        for scope in _SCOPE_PRECEDENCE:
            reference = references.get(scope)
            if reference is None:
                continue
            for memory in await self._memories.list_live(organization_id, scope, reference, now):
                if memory.key in seen_keys:
                    continue
                seen_keys.add(memory.key)
                resolved.append(memory)
        return resolved

    async def as_system_context(
        self,
        organization_id: UUID,
        *,
        conversation_id: UUID | None = None,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> str:
        """Render live memories as a system-context block, or ``""``.

        An empty string when nothing is remembered, so the caller can
        skip adding an empty system turn rather than sending the model
        a heading with nothing under it.
        """
        memories = await self.resolve_memories(
            organization_id,
            conversation_id=conversation_id,
            session_id=session_id,
            user_id=user_id,
            project_id=project_id,
        )
        if not memories:
            return ""
        lines = [f"- {memory.key}: {memory.value}" for memory in memories]
        return "Known context about this user and organization:\n" + "\n".join(lines)

    async def remember(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        scope: MemoryScope,
        scope_reference: str,
        key: str,
        value: str,
        user_id: UUID | None = None,
        importance: float = 0.5,
        expires_at: datetime | None = None,
    ) -> AiMemory:
        """Store or update one remembered fact.

        Updates in place when the key already exists in that scope --
        remembering "preferred region" twice should correct the fact,
        not accumulate two contradictory ones.
        """
        existing = await self._memories.get_by_key(organization_id, scope, scope_reference, key)
        if existing is not None:
            existing.value = value
            existing.importance = importance
            existing.expires_at = expires_at
            return await self._memories.update(existing)

        return await self._memories.create(
            AiMemory(
                organization_id=organization_id,
                project_id=project_id,
                scope=scope,
                scope_reference=scope_reference,
                user_id=user_id,
                key=key,
                value=value,
                importance=importance,
                expires_at=expires_at,
            )
        )

    async def forget_expired(self, organization_id: UUID) -> int:
        """Purge expired memories, returning how many were removed."""
        return await self._memories.delete_expired(organization_id, datetime.now(UTC))

    async def record_turn(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        conversation_id: UUID,
        role: MessageRole,
        content: str,
        model: str | None = None,
        provider: str | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        latency_ms: float | None = None,
        citations: list[dict[str, object]] | None = None,
    ) -> AiMessage:
        """Append one turn to a conversation, numbering it correctly."""
        sequence = await self._messages.next_sequence(conversation_id)
        return await self._messages.create(
            AiMessage(
                organization_id=organization_id,
                project_id=project_id,
                conversation_id=conversation_id,
                sequence=sequence,
                role=role,
                content=content,
                model=model,
                provider=provider,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
                citations=citations or [],
            )
        )


__all__ = ["MemoryService"]
