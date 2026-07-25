"""``organization_audit`` table. Per docs/033 "AUDIT": Organization
Creation, Updates, Deletion, Settings Changes, Branding Changes,
License Changes, Quota Changes, Member Invitations, Administrative
Actions.

Routine column-level Create/Update/Delete auditing for every table is
already automatic via :mod:`shared_core.database.audit`, wired into
``BaseRepository`` itself -- this table adds the "what changed and why"
narrative layer for specifically *privileged* actions, with an explicit
before/after snapshot, matching
``services/rbac-service``'s own ``authorization_audit`` precedent for
recording *why* a privileged action happened, not just that a row
changed.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AuditOutcome


class OrganizationAuditEntry(BaseModel):
    """One audited privileged/administrative action on an organization."""

    __tablename__ = "organization_audit"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
    )

    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    action: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str | None] = mapped_column(String(64), default=None)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    outcome: Mapped[AuditOutcome] = mapped_column(String(8), default=AuditOutcome.SUCCESS)
    reason: Mapped[str] = mapped_column(String(512), default="")
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)


__all__ = ["OrganizationAuditEntry"]
