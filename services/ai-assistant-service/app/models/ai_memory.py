"""``ai_memory`` table -- one durable remembered fact ("MEMORY").

``scope`` decides who it applies to and how long it survives;
``expires_at`` backs "Memory Expiration". A ``CONVERSATION``-scoped
memory dies with its thread, an ``ORGANIZATION``-scoped one persists
across every user in that organization -- which is why scope is a real
column rather than inferred from whichever id happens to be set.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import MemoryScope


class AiMemory(BaseModel):
    """One durable remembered fact."""

    __tablename__ = "ai_memory"

    scope: Mapped[MemoryScope] = mapped_column(String(16), index=True)
    scope_reference: Mapped[str] = mapped_column(String(255), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    key: Mapped[str] = mapped_column(String(255), index=True)
    value: Mapped[str] = mapped_column(Text)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["AiMemory"]
