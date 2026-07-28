"""Repository for :class:`app.models.ai_message.AiMessage`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_message import AiMessage


class AiMessageRepository(BaseRepository[AiMessage]):
    """CRUD plus lookup for :class:`AiMessage`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AiMessage, tenant_scope=tenant_scope)

    async def list_for_conversation(self, conversation_id: UUID) -> list[AiMessage]:
        """Every turn in a conversation, in sequence order."""
        stmt = (
            self._base_select()
            .where(AiMessage.conversation_id == conversation_id)
            .order_by(AiMessage.sequence.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_recent_for_conversation(
        self, conversation_id: UUID, *, limit: int
    ) -> list[AiMessage]:
        """The most recent *limit* turns, returned oldest-first.

        Backs "Context Compression": a long conversation sends only its
        own recent window to the model rather than every turn ever.
        Ordered descending in SQL so the database applies ``LIMIT`` to
        the *newest* rows, then reversed in Python so the caller still
        receives chronological order.
        """
        stmt = (
            self._base_select()
            .where(AiMessage.conversation_id == conversation_id)
            .order_by(AiMessage.sequence.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(reversed(list(result.scalars().all())))

    async def next_sequence(self, conversation_id: UUID) -> int:
        """The next turn number for a conversation.

        Computed in SQL rather than from ``len(messages)`` so it stays
        correct even if a turn is ever soft-deleted.
        """
        stmt = select(func.max(AiMessage.sequence)).where(
            AiMessage.conversation_id == conversation_id
        )
        result = await self._session.execute(stmt)
        current = result.scalar_one_or_none()
        return 0 if current is None else int(current) + 1

    async def list_for_org(self, organization_id: UUID) -> list[AiMessage]:
        """Every message for *organization_id* (analytics rollups)."""
        stmt = self._base_select().where(AiMessage.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AiMessageRepository"]
