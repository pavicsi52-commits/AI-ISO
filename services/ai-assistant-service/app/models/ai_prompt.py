"""``ai_prompts`` table -- a named prompt template
("PROMPT MANAGEMENT": Prompt Templates, Prompt Libraries).

The template body lives in
:class:`~app.models.ai_prompt_version.AiPromptVersion`, not here: a
prompt is an identity that survives across revisions, and putting the
body on the parent would make "Versioning"/"Rollback" impossible
without rewriting history.
"""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class AiPrompt(BaseModel):
    """A named prompt template identity."""

    __tablename__ = "ai_prompts"

    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    current_version_number: Mapped[str] = mapped_column(String(16), default="1.0.0")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["AiPrompt"]
