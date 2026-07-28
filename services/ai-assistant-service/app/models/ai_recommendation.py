"""``ai_recommendations`` table -- one generated recommendation
(docs/046's own AUTOMATION/VALIDATION/MONITORING/CONFIGURATION
assistance sections).

``rationale`` and ``citations`` are stored, not just the conclusion:
an operator asked to accept an AI recommendation about production
infrastructure needs to see why it was made and what it was based on.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import RecommendationStatus, RecommendationType


class AiRecommendation(BaseModel):
    """One generated recommendation."""

    __tablename__ = "ai_recommendations"

    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="SET NULL"), default=None, index=True
    )
    recommendation_type: Mapped[RecommendationType] = mapped_column(String(24), index=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text, default=None)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    confidence: Mapped[float | None] = mapped_column(Float, default=None)
    status: Mapped[RecommendationStatus] = mapped_column(
        String(16), default=RecommendationStatus.PROPOSED, index=True
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(default=None)


__all__ = ["AiRecommendation"]
