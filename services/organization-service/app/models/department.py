"""``organization_departments`` table. Per docs/033 "DEPARTMENTS": CRUD,
Hierarchy, Department Manager, Department Members, Department Metadata,
Department Tags. (Members are tracked via
:class:`~app.models.member.OrganizationMember`'s own ``department_id``,
not a separate join table -- see that model's docstring. Tags/metadata
reuse :class:`~app.models.tag.OrganizationTag`'s generic
``resource_type``/``resource_id`` shape.)
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, ForeignKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column


class Department(BaseModel):
    """One department within an organization, optionally nested under a parent."""

    __tablename__ = "organization_departments"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
    )

    name: Mapped[str] = mapped_column(String(255))
    code: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str | None] = mapped_column(String(2048), default=None)
    parent_department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organization_departments.id", ondelete="SET NULL"), default=None
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


__all__ = ["Department"]
