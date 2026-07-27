"""``validation_categories`` table -- groups
:class:`~app.models.validation_check.ValidationCheck` rows under one of
docs/043's own 20 :class:`~app.models.enums.ValidationType` values, so
a profile/report can roll results up by category (e.g. every
"Security" check) without inspecting each check's own type.
"""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ValidationType


class ValidationCategory(BaseModel):
    """Groups checks under one validation type."""

    __tablename__ = "validation_categories"

    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    validation_type: Mapped[ValidationType] = mapped_column(String(24), index=True)


__all__ = ["ValidationCategory"]
