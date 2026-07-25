"""``authorization_audit`` table. Per docs/032 "AUDIT".

Records every authorization decision, role/permission/policy change,
and privilege-escalation attempt this service makes -- the durable,
queryable trail;
:func:`shared_core.security.audit.audit_security_event` (structured
SIEM-shaped logging) is used alongside this, not instead of it, the
same dual-track pattern ``services/authentication-service`` and
``services/user-management-service`` both established.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AuthorizationDecision, ResourceType


class AuthorizationAuditEntry(BaseModel):
    """One audited authorization decision or administrative action."""

    __tablename__ = "authorization_audit"

    user_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    action: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[ResourceType | None] = mapped_column(String(32), default=None)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    decision: Mapped[AuthorizationDecision] = mapped_column(String(8))
    reason: Mapped[str] = mapped_column(String(512), default="")
    policy_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    role_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    ip_address: Mapped[str | None] = mapped_column(String(64), default=None)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["AuthorizationAuditEntry"]
