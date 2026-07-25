"""Authentication.

Per docs/027_Enterprise_Connector_SDK.md.txt "AUTHENTICATION": Username
Password, SSH Keys, API Keys, OAuth2, JWT, Bearer Tokens, Kerberos,
Certificates, Future SSO. The actual authentication handshake is
entirely protocol-specific (how an SSH key proves identity has nothing
in common with how an OAuth2 token does) -- this module only defines
the shared result shape and a generic :func:`authenticate` wrapper:
validate the credential (:func:`~shared_core.connectors.validation.validate_credential`),
delegate to the provider's own async authenticator callback, and
translate any failure into :class:`~shared_core.connectors.exceptions.AuthenticationFailedError`
uniformly.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from shared_core.connectors.credentials import Credential
from shared_core.connectors.exceptions import AuthenticationFailedError
from shared_core.connectors.validation import validate_credential

Authenticator = Callable[[Credential], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    """The outcome of one :func:`authenticate` call."""

    succeeded: bool
    authenticated_at: datetime
    identity: str | None = None
    error: str | None = None


async def authenticate(
    credential: Credential, authenticator: Authenticator
) -> AuthenticationResult:
    """Validate *credential*, then run *authenticator* against it.

    Raises:
        AuthenticationFailedError: If validation fails, or *authenticator* raises.
    """
    validate_credential(credential)
    try:
        await authenticator(credential)
    except Exception as exc:
        raise AuthenticationFailedError(f"Authentication failed: {exc}") from exc
    return AuthenticationResult(
        succeeded=True, authenticated_at=datetime.now(UTC), identity=credential.identity
    )


__all__ = ["AuthenticationResult", "Authenticator", "authenticate"]
