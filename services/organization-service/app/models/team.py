"""``organization_teams`` table. Per docs/033 "TEAMS": CRUD, Members,
Team Leads, Projects, Tags, Metadata.

"Projects" is a cross-reference only (bare ids in ``metadata_``, per
docs/033's own "DO NOT IMPLEMENT": Project Management -- this service
tracks team membership, not project assignments). "Members" are
tracked via :class:`~app.models.member.OrganizationMember`'s own
``team_id``, not a separate join table.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, ForeignKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column


class Team(BaseModel):
    """One team within an organization, optionally under a department/business unit."""

    __tablename__ = "organization_teams"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
    )

    name: Mapped[str] = mapped_column(String(255))
    code: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str | None] = mapped_column(String(2048), default=None)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organization_departments.id", ondelete="SET NULL"), default=None
    )
    business_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organization_business_units.id", ondelete="SET NULL"), default=None
    )
    team_lead_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


__all__ = ["Team"]
