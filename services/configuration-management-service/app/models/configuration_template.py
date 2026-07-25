"""``configuration_templates`` table. Per docs/039's REST APIs list
(``GET/POST /configurations/templates``) -- a reusable content template
a profile/version can be generated from, parameterized by
``variables_schema``.
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ConfigurationType


class ConfigurationTemplate(BaseModel):
    """One reusable configuration template."""

    __tablename__ = "configuration_templates"

    template_name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(String(2048), default=None)
    configuration_type: Mapped[ConfigurationType] = mapped_column(String(24), index=True)
    content: Mapped[str] = mapped_column(Text)
    variables_schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["ConfigurationTemplate"]
