"""``validation_templates`` table -- a reusable, pre-built starting
point for creating a new :class:`~app.models.validation_profile
.ValidationProfile` ("Reusable Templates"). ``template_content`` embeds
a full default ``check_ids``/``target_types``/``scoring_weights``
shape a caller copies into a new profile at creation time -- templates
are never executed directly, only profiles are.

``authored_by`` is a free-text display name, deliberately not named
``created_by`` -- ``BaseEntityMixin`` already reserves that name for
its own ``UUID``-typed audit-trail column ("No future entity may
redefine these fields"), so a second, differently-typed field needed
its own distinct name.
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ValidationProfileType


class ValidationTemplate(BaseModel):
    """A reusable starting point for creating a new validation profile."""

    __tablename__ = "validation_templates"

    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    profile_type: Mapped[ValidationProfileType] = mapped_column(String(24), index=True)
    template_content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_system_template: Mapped[bool] = mapped_column(Boolean, default=False)
    authored_by: Mapped[str | None] = mapped_column(String(255), default=None)


__all__ = ["ValidationTemplate"]
