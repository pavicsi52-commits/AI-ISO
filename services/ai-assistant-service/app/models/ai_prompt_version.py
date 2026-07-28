"""``ai_prompt_versions`` table -- one immutable revision of a prompt
("PROMPT MANAGEMENT": Versioning, Testing, Approval, Rollback,
Variables).

Rollback is a matter of pointing the parent's own
``current_version_number`` at an earlier row; nothing is ever edited in
place, so an approved revision stays exactly as approved.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import PromptStatus


class AiPromptVersion(BaseModel):
    """One immutable revision of a prompt template."""

    __tablename__ = "ai_prompt_versions"

    prompt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_prompts.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[str] = mapped_column(String(16), index=True)
    template: Mapped[str] = mapped_column(Text)
    variables: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[PromptStatus] = mapped_column(String(16), default=PromptStatus.DRAFT, index=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["AiPromptVersion"]
