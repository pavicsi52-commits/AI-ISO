"""``ai_tool_calls`` table -- one invocation the model requested.

Separate from :class:`~app.models.ai_tool_result.AiToolResult` because
docs/046's own table list names both: a call is the *request* (with its
own arguments and authorization outcome), a result is what came back.
A ``DENIED`` call has no result at all, which is exactly the audit
trail "Permission-aware Tool Calls" needs.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ToolCallStatus


class AiToolCall(BaseModel):
    """One tool invocation requested by the model."""

    __tablename__ = "ai_tool_calls"

    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"), default=None, index=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_messages.id", ondelete="SET NULL"), default=None, index=True
    )
    tool_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_tools.id", ondelete="CASCADE"), index=True
    )
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[ToolCallStatus] = mapped_column(
        String(16), default=ToolCallStatus.PENDING, index=True
    )
    denial_reason: Mapped[str | None] = mapped_column(Text, default=None)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["AiToolCall"]
