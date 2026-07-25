"""SQLAlchemy models for the authentication service.

Every model must be imported here so it registers with
:data:`shared_core.database.base.Base.metadata` -- both Alembic
autogenerate and ``Base.metadata.create_all()`` (used by the SQLite
test engine) rely on every table being known before they run.
"""

from __future__ import annotations

from app.models.apikey import ApiKey
from app.models.audit import AuthenticationAuditEntry
from app.models.credentials import UserCredential
from app.models.email_verification import EmailVerificationToken
from app.models.failed_login import FailedLoginEntry
from app.models.login_history import LoginHistoryEntry
from app.models.mfa import MfaDevice
from app.models.password import PasswordHistoryEntry, PasswordResetToken
from app.models.service_account import ServiceAccount
from app.models.session import Session
from app.models.token import AccessToken, RefreshToken
from app.models.trusted_device import TrustedDevice
from app.models.user import User

__all__ = [
    "AccessToken",
    "ApiKey",
    "AuthenticationAuditEntry",
    "EmailVerificationToken",
    "FailedLoginEntry",
    "LoginHistoryEntry",
    "MfaDevice",
    "PasswordHistoryEntry",
    "PasswordResetToken",
    "RefreshToken",
    "ServiceAccount",
    "Session",
    "TrustedDevice",
    "User",
    "UserCredential",
]
