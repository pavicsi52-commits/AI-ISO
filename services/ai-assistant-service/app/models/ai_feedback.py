"""``ai_feedback`` table -- a user's own rating of an assistant turn
("ANALYTICS": Feedback Scores, Recommendation Accuracy).
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import FeedbackRating


class AiFeedback(BaseModel):
    """One user rating of an assistant turn."""

    __tablename__ = "ai_feedback"

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_messages.id", ondelete="CASCADE"), index=True
    )
    rating: Mapped[FeedbackRating] = mapped_column(String(16), index=True)
    comment: Mapped[str | None] = mapped_column(Text, default=None)
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(default=None)


__all__ = ["AiFeedback"]
