"""Security-framework-specific exceptions.

Each subclasses the matching Prompt 015 base
(:class:`~shared_core.exceptions.AuthenticationError` or
:class:`~shared_core.exceptions.AuthorizationError`) so a bare
``except AuthenticationError`` still catches everything. Not registered
in :mod:`shared_core.exceptions.constants`'s central catalog --
:mod:`shared_core.exceptions` already has plenty of subpackages depending
on it (including :mod:`shared_core.security` itself, for
``AuthenticationError``/``AuthorizationError``), so having the catalog
import back from here would cycle. Error codes are still manually kept
unique against the rest of the ``AIIOS-AUTH-*``/``AIIOS-AUTHZ-*`` range
(the same approach :mod:`shared_core.config.exceptions` uses for
``AIIOS-CONFIG-*``).
"""

from __future__ import annotations

from shared_core.exceptions.authentication import AuthenticationError
from shared_core.exceptions.authorization import AuthorizationError


class SessionExpiredError(AuthenticationError):
    """Raised when a session has passed its idle or absolute timeout."""

    error_code = "AIIOS-AUTH-0002"
    default_user_message = "Your session has expired. Please sign in again."


class SessionRevokedError(AuthenticationError):
    """Raised when a session was explicitly revoked."""

    error_code = "AIIOS-AUTH-0003"
    default_user_message = "Your session has been revoked. Please sign in again."


class TokenRevokedError(AuthenticationError):
    """Raised when a JWT's ``jti`` is found in the revocation store."""

    error_code = "AIIOS-AUTH-0004"
    default_user_message = "This token has been revoked. Please sign in again."


class MfaRequiredError(AuthenticationError):
    """Raised when an action requires MFA that the caller hasn't completed."""

    error_code = "AIIOS-AUTH-0005"
    default_user_message = "Multi-factor authentication is required to continue."


class InvalidMfaCodeError(AuthenticationError):
    """Raised when a submitted TOTP/email-OTP/recovery code doesn't verify."""

    error_code = "AIIOS-AUTH-0006"
    default_user_message = "The multi-factor authentication code is invalid."


class CertificateExpiredError(AuthenticationError):
    """Raised when a certificate presented for authentication has expired."""

    error_code = "AIIOS-AUTH-0007"
    default_user_message = "The certificate has expired."


class CsrfValidationError(AuthorizationError):
    """Raised when a CSRF token is missing or doesn't match."""

    error_code = "AIIOS-AUTHZ-0002"
    default_user_message = "The request could not be verified. Please refresh and try again."
