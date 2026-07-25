"""Repositories for the authentication service, one per entity."""

from __future__ import annotations

from app.repositories.apikey import ApiKeyRepository
from app.repositories.audit import AuthenticationAuditRepository
from app.repositories.credentials import UserCredentialRepository
from app.repositories.device import TrustedDeviceRepository
from app.repositories.failed_login import FailedLoginRepository
from app.repositories.login_history import LoginHistoryRepository
from app.repositories.mfa import MfaDeviceRepository
from app.repositories.password import PasswordHistoryRepository, PasswordResetTokenRepository
from app.repositories.service_account import ServiceAccountRepository
from app.repositories.session import SessionRepository
from app.repositories.token import AccessTokenRepository, RefreshTokenRepository
from app.repositories.user import UserRepository
from app.repositories.verification import EmailVerificationTokenRepository

__all__ = [
    "AccessTokenRepository",
    "ApiKeyRepository",
    "AuthenticationAuditRepository",
    "EmailVerificationTokenRepository",
    "FailedLoginRepository",
    "LoginHistoryRepository",
    "MfaDeviceRepository",
    "PasswordHistoryRepository",
    "PasswordResetTokenRepository",
    "RefreshTokenRepository",
    "ServiceAccountRepository",
    "SessionRepository",
    "TrustedDeviceRepository",
    "UserCredentialRepository",
    "UserRepository",
]
