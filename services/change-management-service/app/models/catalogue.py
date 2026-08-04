"""``change_categories``, ``change_types``, ``change_priorities``, ``change_status``.

The organization-configurable display and policy-override layer that
sits beside the platform's built-in enum vocabulary in
``app/models/enums.py``. An organization renames, reorders, and colours
these for its own dashboards without the enum itself becoming customer
data -- the same split Prompt 050 established for
``PolicyCategoryRecord`` and Prompt 052 carried forward for
``IncidentCategoryRecord``.
"""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ChangeCategory, ChangePriority, ChangeStatus, ChangeType


class ChangeCategoryRecord(BaseModel):
    """``change_categories`` -- a named grouping an organization defines."""

    __tablename__ = "change_categories"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_change_category_slug"),)

    slug: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[ChangeCategory] = mapped_column(
        String(64), default=ChangeCategory.CUSTOM, index=True
    )
    display_order: Mapped[int] = mapped_column(Integer, default=0)


class ChangeTypeRecord(BaseModel):
    """``change_types`` -- an organization's own policy defaults per process type.

    A row's absence is not an error -- ``app/changes/engine.py`` has its
    own platform defaults for what each :class:`~app.models.enums
    .ChangeType` requires -- so an organization only needs a row here to
    override one.
    """

    __tablename__ = "change_types"
    __table_args__ = (UniqueConstraint("organization_id", "change_type", name="uq_change_type"),)

    change_type: Mapped[ChangeType] = mapped_column(String(32), index=True)
    label: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    requires_cab: Mapped[bool | None] = mapped_column(Boolean, default=None)
    requires_risk_assessment: Mapped[bool | None] = mapped_column(Boolean, default=None)
    display_order: Mapped[int] = mapped_column(Integer, default=0)


class ChangePriorityRecord(BaseModel):
    """``change_priorities`` -- an organization's own approval-window overrides."""

    __tablename__ = "change_priorities"
    __table_args__ = (UniqueConstraint("organization_id", "priority", name="uq_change_priority"),)

    priority: Mapped[ChangePriority] = mapped_column(String(32), index=True)
    label: Mapped[str] = mapped_column(String(128))
    approval_window_hours: Mapped[int | None] = mapped_column(Integer, default=None)
    color: Mapped[str | None] = mapped_column(String(32), default=None)


class ChangeStatusRecord(BaseModel):
    """``change_status`` -- display metadata for a lifecycle status.

    Never changes what the status *means* -- ``app/changes/engine.py``
    owns the transition graph and nothing here can widen it -- only how
    it is labelled and coloured on a board.
    """

    __tablename__ = "change_status"
    __table_args__ = (
        UniqueConstraint("organization_id", "status", name="uq_change_status_record"),
    )

    status: Mapped[ChangeStatus] = mapped_column(String(32), index=True)
    label: Mapped[str] = mapped_column(String(128))
    color: Mapped[str | None] = mapped_column(String(32), default=None)
    display_order: Mapped[int] = mapped_column(Integer, default=0)


__all__ = [
    "ChangeCategoryRecord",
    "ChangePriorityRecord",
    "ChangeStatusRecord",
    "ChangeTypeRecord",
]
