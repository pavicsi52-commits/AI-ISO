"""``permission_groups`` table. Per docs/032 "PERMISSION GROUPS"."""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import PermissionGroupCategory


class PermissionGroup(BaseModel):
    """A named collection permissions can be organized under."""

    __tablename__ = "permission_groups"

    name: Mapped[str] = mapped_column(String(128))
    code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(1024), default=None)
    category: Mapped[PermissionGroupCategory] = mapped_column(
        String(32), default=PermissionGroupCategory.CUSTOM
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


__all__ = ["PermissionGroup"]
