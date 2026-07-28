"""``report_categories`` table -- the taxonomy reports are filed under."""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ReportCategory


class ReportCategoryRecord(BaseModel):
    """One report category.

    docs/047 fixes the *vocabulary* (:class:`ReportCategory`) but still
    calls for a ``report_categories`` table, because an organization
    needs its own display name, description, and ordering over that
    vocabulary -- and ``CUSTOM`` is explicitly one of the members, which
    only means anything if a row can name it.
    """

    __tablename__ = "report_categories"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_report_category_org_slug"),
    )

    category: Mapped[ReportCategory] = mapped_column(String(24), index=True)
    slug: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    display_order: Mapped[int] = mapped_column(default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["ReportCategoryRecord"]
