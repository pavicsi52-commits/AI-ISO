"""``authentication_audit`` table.

Per docs/030 "AUDIT": Every Login, Every Logout, Failed Login,
Password Change, Session Revocation, Token Creation, Token Revocation,
MFA Changes, API Key Usage. Reuses
:class:`shared_core.enums.audit_action.AuditAction` (already covers
``LOGIN``/``LOGOUT``/``LOGIN_FAILED``/``PASSWORD_CHANGED``) rather than
a parallel service-local action enum.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from shared_core.enums.audit_action import AuditAction
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class AuthenticationAuditEntry(BaseModel):
    """One audited authentication-related event."""

    __tablename__ = "authentication_audit"

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), default=None)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    action: Mapped[AuditAction] = mapped_column(String(32))
    ip_address: Mapped[str | None] = mapped_column(String(64), default=None)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)


__all__ = ["AuthenticationAuditEntry"]
