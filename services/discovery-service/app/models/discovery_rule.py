"""``discovery_rules`` table -- include/exclude/classification/
relationship/assignment rules evaluated during discovery processing.

:attr:`is_enabled` (not ``is_active``) -- see
``app/models/discovery_filter.py``'s own docstring for the
column-name-collision class this avoids.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import RuleType


class DiscoveryRule(BaseModel):
    """One include/exclude/classification/relationship/assignment rule."""

    __tablename__ = "discovery_rules"

    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("discovery_profiles.id", ondelete="CASCADE"), default=None
    )
    rule_type: Mapped[RuleType] = mapped_column(String(24), index=True)
    field: Mapped[str] = mapped_column(String(128))
    operator: Mapped[str] = mapped_column(String(16), default="eq")
    value: Mapped[Any] = mapped_column(JSON, default=None)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["DiscoveryRule"]
