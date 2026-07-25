"""Authentication audit trail.

Per docs/030 "AUDIT": Every Login, Every Logout, Failed Login,
Password Change, Session Revocation, Token Creation, Token Revocation,
MFA Changes, API Key Usage. Every event is both (a) logged through
:func:`shared_core.security.audit.audit_security_event` where a
matching :class:`~shared_core.security.audit.SecurityAuditEventType`
exists (SIEM-shaped structured logging, Prompt 017) and (b) persisted
to this service's own ``authentication_audit`` table (the durable,
queryable trail docs/030 "DATABASE TABLES" requires) via
:class:`~app.repositories.audit.AuthenticationAuditRepository`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.enums.audit_action import AuditAction
from shared_core.security.audit import SecurityAuditEventType, audit_security_event

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.audit import AuthenticationAuditEntry
from app.repositories.audit import AuthenticationAuditRepository

_SECURITY_EVENT_MAP: dict[AuditAction, SecurityAuditEventType] = {
    AuditAction.LOGIN: SecurityAuditEventType.LOGIN,
    AuditAction.LOGOUT: SecurityAuditEventType.LOGOUT,
    AuditAction.LOGIN_FAILED: SecurityAuditEventType.FAILED_LOGIN,
    AuditAction.PASSWORD_CHANGED: SecurityAuditEventType.PASSWORD_CHANGE,
}


class AuditService:
    """Records every authentication-related event, structured-logged and persisted."""

    def __init__(self, entries: AuthenticationAuditRepository) -> None:
        self._entries = entries

    async def record(
        self,
        action: AuditAction,
        *,
        user_id: UUID | None = None,
        actor_id: UUID | None = None,
        ip_address: str | None = None,
        outcome: str = "success",
        **detail: Any,
    ) -> None:
        """Record one audited authentication event."""
        security_event = _SECURITY_EVENT_MAP.get(action)
        if security_event is not None:
            audit_security_event(
                security_event,
                actor_id=str(actor_id) if actor_id is not None else None,
                outcome=outcome,
                ip_address=ip_address,
                **detail,
            )
        await self._entries.create(
            AuthenticationAuditEntry(
                user_id=user_id,
                actor_id=actor_id,
                action=action,
                ip_address=ip_address,
                detail={"outcome": outcome, **detail},
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )


__all__ = ["AuditService"]
