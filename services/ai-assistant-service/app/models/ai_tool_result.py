"""``ai_tool_results`` table -- what one tool invocation returned.

``result`` is stored as JSON regardless of the tool's own native shape
so it can be fed straight back into the model's own context as a
``TOOL``-role message without a per-tool serializer.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column


class AiToolResult(BaseModel):
    """What one tool invocation returned."""

    __tablename__ = "ai_tool_results"

    tool_call_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_tool_calls.id", ondelete="CASCADE"), index=True
    )
    succeeded: Mapped[bool] = mapped_column(Boolean, default=True)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    duration_ms: Mapped[float | None] = mapped_column(Float, default=None)


__all__ = ["AiToolResult"]
