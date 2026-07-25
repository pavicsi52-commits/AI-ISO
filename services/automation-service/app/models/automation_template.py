"""``automation_templates`` table. Per docs/040's REST APIs list
(``GET/POST /automation/templates``) -- a reusable content template a
job can be generated from, parameterized by ``variables_schema``, the
same shape
``services/configuration-management-service``'s own
``ConfigurationTemplate`` established.
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import PlaybookType


class AutomationTemplate(BaseModel):
    """One reusable automation content template."""

    __tablename__ = "automation_templates"

    template_name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(String(2048), default=None)
    playbook_type: Mapped[PlaybookType] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text)
    variables_schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["AutomationTemplate"]
