"""``organization_business_units`` table. Per docs/033 "BUSINESS UNITS":
CRUD, Hierarchy, Business Unit Owner, Departments, Teams, Metadata.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, ForeignKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column


class BusinessUnit(BaseModel):
    """One business unit within an organization, optionally nested under a parent."""

    __tablename__ = "organization_business_units"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
    )

    name: Mapped[str] = mapped_column(String(255))
    code: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str | None] = mapped_column(String(2048), default=None)
    parent_business_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organization_business_units.id", ondelete="SET NULL"), default=None
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


__all__ = ["BusinessUnit"]
