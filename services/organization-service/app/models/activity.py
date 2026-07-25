"""``organization_activity`` table -- the narrative activity feed.

Per docs/033's own 19-table list, distinct from
:class:`~app.models.audit.OrganizationAuditEntry` (privileged/
administrative action trail) the same way
``services/user-management-service``'s ``UserActivityEntry`` is
distinct from routine column-level audit -- this is "what happened and
why," not a security record.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import OrganizationActivityType


class OrganizationActivityEntry(BaseModel):
    """One narrative activity-feed entry for an organization."""

    __tablename__ = "organization_activity"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
    )

    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    activity_type: Mapped[OrganizationActivityType] = mapped_column(String(32), index=True)
    description: Mapped[str | None] = mapped_column(String(1024), default=None)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["OrganizationActivityEntry"]
