"""Security audit event logging.

Per docs/017_Enterprise_Security_Framework.md.txt "SECURITY AUDIT": every
listed event type flows through
:meth:`shared_core.logging.logger.AIIOSLogger.security` (Prompt 014) with
a stable, structured shape -- one place, one shape, so a downstream SIEM
or audit dashboard can rely on it rather than parsing free-text log lines.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from shared_core.logging.logger import get_logger

logger = get_logger("shared_core.security.audit")


class SecurityAuditEventType(StrEnum):
    """Every security event type docs/017 "SECURITY AUDIT" lists."""

    LOGIN = "login"
    LOGOUT = "logout"
    FAILED_LOGIN = "failed_login"
    PERMISSION_DENIED = "permission_denied"
    PASSWORD_CHANGE = "password_change"
    API_KEY_CREATED = "api_key_created"
    SECRET_ACCESS = "secret_access"
    ROLE_CHANGE = "role_change"
    PERMISSION_CHANGE = "permission_change"
    MFA_ENABLED = "mfa_enabled"
    MFA_DISABLED = "mfa_disabled"
    SESSION_REVOKED = "session_revoked"
    SECURITY_POLICY_CHANGED = "security_policy_changed"


def audit_security_event(
    event_type: SecurityAuditEventType,
    *,
    actor_id: str | None = None,
    outcome: str = "success",
    **fields: Any,
) -> None:
    """Log a security audit event with a stable, structured shape."""
    logger.security(event_type.value, outcome=outcome, actor_id=actor_id, **fields)
