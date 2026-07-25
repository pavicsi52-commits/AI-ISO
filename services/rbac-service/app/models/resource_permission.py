"""``resource_permissions`` table -- direct, per-instance authorization.

Per docs/032 "RESOURCE AUTHORIZATION": Resource Owner, Shared
Resources, Public Resources, Private Resources, Inherited Permissions.
A grant (or explicit deny) of one permission to one subject (a user or
a role) on one concrete resource instance, layered on top of the
role/permission catalog rather than replacing it -- see
:mod:`app.services.resource_authorization`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import PolicyEffect, ResourceType, SubjectType


class ResourcePermission(BaseModel):
    """One direct authorization grant/deny on one resource instance."""

    __tablename__ = "resource_permissions"

    resource_type: Mapped[ResourceType] = mapped_column(String(32), index=True)
    resource_id: Mapped[uuid.UUID] = mapped_column(index=True)
    subject_type: Mapped[SubjectType] = mapped_column(String(16))
    subject_id: Mapped[uuid.UUID] = mapped_column(index=True)
    permission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE")
    )
    effect: Mapped[PolicyEffect] = mapped_column(String(8), default=PolicyEffect.ALLOW)
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["ResourcePermission"]
