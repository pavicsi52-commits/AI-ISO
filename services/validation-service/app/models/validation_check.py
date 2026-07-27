"""``validation_checks`` table -- a standalone, reusable definition of
one thing to inspect on a target ("Reusable Check Libraries"),
referenced by id from any number of
:class:`~app.models.validation_profile.ValidationProfile` rows.
``collector_key`` names which function in ``app/collectors/`` gathers
the raw data this check needs (e.g. ``"disk_usage"``); ``parameters``
carries check-specific arguments for that collector (e.g. ``{"port":
443}`` for a ``PORTS`` check). A check only *collects* data -- whether
the collected value passes or fails is a separate concern, evaluated
by the one or more :class:`~app.models.validation_rule.ValidationRule`
rows that reference this check's own id.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ValidationCheckType


class ValidationCheck(BaseModel):
    """A standalone, reusable definition of one thing to inspect on a target."""

    __tablename__ = "validation_checks"

    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("validation_categories.id", ondelete="SET NULL"), default=None, index=True
    )
    check_type: Mapped[ValidationCheckType] = mapped_column(String(24), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    collector_key: Mapped[str] = mapped_column(String(64))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    timeout_seconds: Mapped[float] = mapped_column(Float, default=30.0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)


__all__ = ["ValidationCheck"]
