"""Conversation and session reads.

Separate from :mod:`app.services.chat`, which *runs* a turn: this is
the read side backing ``GET /ai/conversations``, and keeping them apart
means listing history never risks touching the model.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.ai_conversation import AiConversation
from app.models.ai_message import AiMessage
from app.models.ai_session import AiSession
from app.repositories.ai_conversation import AiConversationRepository
from app.repositories.ai_message import AiMessageRepository
from app.repositories.ai_session import AiSessionRepository


class ConversationService:
    """Reads conversations, their turns, and their sessions."""

    def __init__(
        self,
        conversations: AiConversationRepository,
        messages: AiMessageRepository,
        sessions: AiSessionRepository,
    ) -> None:
        self._conversations = conversations
        self._messages = messages
        self._sessions = sessions

    async def get_by_id(self, conversation_id: UUID) -> AiConversation:
        """Return one conversation.

        Raises:
            NotFoundError: If no such conversation exists.
        """
        return await self._conversations.require_by_id(conversation_id)

    async def list_for_org(self, organization_id: UUID) -> list[AiConversation]:
        """Every conversation for *organization_id*."""
        return await self._conversations.list_for_org(organization_id)

    async def list_for_user(self, organization_id: UUID, user_id: UUID) -> list[AiConversation]:
        """Every conversation belonging to one user, most recent first."""
        return await self._conversations.list_for_user(organization_id, user_id)

    async def list_messages(self, conversation_id: UUID) -> list[AiMessage]:
        """Every turn in a conversation, in order."""
        return await self._messages.list_for_conversation(conversation_id)

    async def open_session(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        user_id: UUID,
        label: str | None = None,
        expires_at: datetime | None = None,
    ) -> AiSession:
        """Open a new working session."""
        now = datetime.now(UTC)
        return await self._sessions.create(
            AiSession(
                organization_id=organization_id,
                project_id=project_id,
                user_id=user_id,
                label=label,
                started_at=now,
                last_active_at=now,
                expires_at=expires_at,
                is_open=True,
            )
        )

    async def list_sessions(
        self, organization_id: UUID, *, user_id: UUID | None = None, open_only: bool = False
    ) -> list[AiSession]:
        """Sessions for an organization, optionally narrowed to one user.

        ``open_only`` is the common case in a UI -- "which of my
        assistant sessions are still live?" -- and is pushed into SQL
        rather than filtered in Python so a long history stays cheap.
        """
        if user_id is not None and open_only:
            return await self._sessions.list_open_for_user(organization_id, user_id)
        sessions = await self._sessions.list_for_org(organization_id)
        if user_id is not None:
            sessions = [session for session in sessions if session.user_id == user_id]
        if open_only:
            sessions = [session for session in sessions if session.is_open]
        return sessions

    async def touch_session(self, session_id: UUID) -> AiSession:
        """Record activity on a session.

        Raises:
            NotFoundError: If no such session exists.
        """
        session = await self._sessions.require_by_id(session_id)
        session.last_active_at = datetime.now(UTC)
        return await self._sessions.update(session)

    async def close_session(self, session_id: UUID) -> AiSession:
        """Close a session.

        Raises:
            NotFoundError: If no such session exists.
        """
        session = await self._sessions.require_by_id(session_id)
        session.is_open = False
        return await self._sessions.update(session)


__all__ = ["ConversationService"]
