"""``configuration_change_sets`` table. Per docs/039 "VERSIONING"
"Change Tracking" -- a grouped, reviewable set of field-level changes
applied together, distinct from :mod:`app.models.configuration_version`'s
own full-state snapshots (a change set is the diff that *produces* the
next version).

"Who created this change set" is already
:class:`~shared_core.base.AuditMixin`'s own inherited ``created_by``
column via :class:`~shared_core.database.base.BaseModel` -- no
service-local column redeclares it (see
:mod:`app.models.configuration_backup`'s own docstring for the bug
class this avoids).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ChangeSetStatus


class ConfigurationChangeSet(BaseModel):
    """One grouped set of field-level changes to a configuration profile."""

    __tablename__ = "configuration_change_sets"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("configuration_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[ChangeSetStatus] = mapped_column(
        String(16), default=ChangeSetStatus.DRAFT, index=True
    )
    changes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["ConfigurationChangeSet"]
