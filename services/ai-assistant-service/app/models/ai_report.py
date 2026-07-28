"""``ai_reports`` table -- one generated report ("REPORT GENERATION")."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AiReportType


class AiReport(BaseModel):
    """One generated report."""

    __tablename__ = "ai_reports"

    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="SET NULL"), default=None, index=True
    )
    report_type: Mapped[AiReportType] = mapped_column(String(24), index=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    generated_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["AiReport"]
