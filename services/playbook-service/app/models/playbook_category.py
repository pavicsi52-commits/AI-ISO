"""``playbook_categories`` table. Per docs/041 "REPOSITORY" "Support": Categories."""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column


class PlaybookCategory(BaseModel):
    """One organizational category playbooks can be filed under."""

    __tablename__ = "playbook_categories"

    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["PlaybookCategory"]
