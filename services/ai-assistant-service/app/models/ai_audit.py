"""``ai_audit`` table. Per docs/046 "AUDIT": Prompt Changes, Tool Calls,
Recommendations, Model Selection, Conversation Access, Administrative
Operations. Class named ``AiAuditEntry`` matching every prior AI-IOS
service's own convention.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AuditOutcome


class AiAuditEntry(BaseModel):
    """One privileged/administrative action recorded against AI configuration."""

    __tablename__ = "ai_audit"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    outcome: Mapped[AuditOutcome] = mapped_column(String(16), default=AuditOutcome.SUCCESS)
    reason: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)


__all__ = ["AiAuditEntry"]
