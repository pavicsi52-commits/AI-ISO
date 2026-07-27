"""``playbook_templates`` table, per docs/041's own REST APIs list
(``GET/POST /playbooks/templates``).
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ContentType


class PlaybookTemplate(BaseModel):
    """One reusable automation content template."""

    __tablename__ = "playbook_templates"

    template_name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    content_type: Mapped[ContentType] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text)
    variables_schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["PlaybookTemplate"]
