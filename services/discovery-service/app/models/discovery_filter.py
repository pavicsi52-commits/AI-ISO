"""``discovery_filters`` table -- a named, reusable filter criteria set,
applied to targets, assets, or relationships.

:attr:`is_enabled` (not ``is_active``) -- ``is_active`` is already
:class:`~shared_core.base.BaseEntityMixin`'s own inherited soft-delete
column via :class:`~shared_core.database.base.BaseModel`; a
same-named domain flag here would silently collide with it, the exact
bug already caught and fixed for
``services/discovery-service/app/models/discovery_schedule.py``'s own
``DiscoverySchedule.is_enabled`` -- found again by a later audit
across every AI-IOS service's models for the same collision class.
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import FilterAppliesTo


class DiscoveryFilter(BaseModel):
    """One named, reusable filter criteria set."""

    __tablename__ = "discovery_filters"

    name: Mapped[str] = mapped_column(String(255), index=True)
    applies_to: Mapped[FilterAppliesTo] = mapped_column(String(16), index=True)
    filter_criteria: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["DiscoveryFilter"]
