"""``project_audit`` table -- privileged-action audit trail for a project,
mirroring ``services/organization-service``'s identical
``OrganizationAuditEntry`` shape. Per docs/034 "AUDIT": Project
Creation, Updates, Deletion, Membership Changes, Role Changes,
Ownership Changes, Settings Updates, Template Usage, Resource Linking,
Administrative Operations.

Routine column-level Create/Update/Delete auditing for every table is
already automatic via :mod:`shared_core.database.audit`, wired into
``BaseRepository`` itself -- this records specifically *privileged*
actions with a before/after snapshot, the same distinction
``app/models/project_activity.py``'s narrative feed doesn't attempt.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AuditOutcome


class ProjectAuditEntry(BaseModel):
    """One privileged/administrative action recorded against a project."""

    __tablename__ = "project_audit"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    action: Mapped[str] = mapped_column(String(128))
    resource_type: Mapped[str | None] = mapped_column(String(64), default=None)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    outcome: Mapped[AuditOutcome] = mapped_column(String(16), default=AuditOutcome.SUCCESS)
    reason: Mapped[str] = mapped_column(String(1024), default="")
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)


__all__ = ["ProjectAuditEntry"]
