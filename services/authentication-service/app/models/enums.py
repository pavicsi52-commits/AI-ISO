"""Enums specific to the authentication service's own database schema.

``Role``/``Permission`` (RBAC) already exist in
``shared_core.enums`` and are reused as-is elsewhere in this
service; these are the enums that don't exist yet anywhere in
``shared_core``.
"""

from __future__ import annotations

from enum import StrEnum


class CredentialType(StrEnum):
    """The kind of credential one ``user_credentials`` row represents.

    Only ``PASSWORD`` is used in this phase -- OAuth2/OIDC/LDAP/Active
    Directory/SAML federation is deferred to a follow-up phase, per the
    scope decision recorded in this package's README.
    """

    PASSWORD = "password"


class TokenType(StrEnum):
    """Which kind of JWT one issued-token row tracks."""

    ACCESS = "access"
    REFRESH = "refresh"


class MfaDeviceType(StrEnum):
    """The kind of second factor one ``mfa_devices`` row represents.

    Only ``TOTP`` is supported today -- WebAuthn/FIDO2 are explicit
    future work per docs/030 "MULTI-FACTOR AUTHENTICATION".
    """

    TOTP = "totp"


class AuthMethod(StrEnum):
    """How one login attempt authenticated (or attempted to)."""

    PASSWORD = "password"
    REFRESH_TOKEN = "refresh_token"
    API_KEY = "api_key"
    SERVICE_ACCOUNT = "service_account"


class FailedLoginReason(StrEnum):
    """Why one login attempt failed."""

    INVALID_CREDENTIALS = "invalid_credentials"
    ACCOUNT_NOT_FOUND = "account_not_found"
    ACCOUNT_LOCKED = "account_locked"
    ACCOUNT_INACTIVE = "account_inactive"
    EMAIL_NOT_VERIFIED = "email_not_verified"
    MFA_FAILED = "mfa_failed"


__all__ = [
    "AuthMethod",
    "CredentialType",
    "FailedLoginReason",
    "MfaDeviceType",
    "TokenType",
]
