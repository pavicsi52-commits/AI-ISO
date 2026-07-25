"""Authentication orchestration: combines JWT and API key verification into one entry point.

Per docs/017_Enterprise_Security_Framework.md.txt "DO NOT IMPLEMENT":
"Authentication Service" -- this is the framework a real auth service
calls into, not a running service itself. No user lookup, no database
access: callers supply whatever this framework can't know on its own
(e.g. an ``ApiKeyRecord`` looked up by the caller's own repository).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shared_core.exceptions.authentication import AuthenticationError
from shared_core.security.apikey import ApiKeyRecord, hash_api_key, is_api_key_usable
from shared_core.security.jwt import decode_token


@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    """The outcome of successfully authenticating a caller."""

    subject: str
    method: str
    claims: dict[str, Any] = field(default_factory=dict)


def authenticate_with_jwt(
    token: str, *, public_key: str, **decode_kwargs: Any
) -> AuthenticationResult:
    """Authenticate a caller via a JWT access token.

    Raises:
        AuthenticationError: If the token doesn't verify, or has no
            ``sub`` claim to identify the caller.
    """
    claims = decode_token(token, public_key=public_key, **decode_kwargs)
    subject = claims.get("sub")
    if not subject:
        raise AuthenticationError("Token is missing a 'sub' claim.")
    return AuthenticationResult(subject=subject, method="jwt", claims=claims)


def authenticate_with_api_key(raw_key: str, *, record: ApiKeyRecord | None) -> AuthenticationResult:
    """Authenticate a caller via an API key.

    The caller looks up *record* (by ``hash_api_key(raw_key)``) themselves
    -- this framework has no database access -- and passes it in.

    Raises:
        AuthenticationError: If *record* is missing, doesn't match
            *raw_key*, or is expired/revoked.
    """
    if record is None or record.hashed_key != hash_api_key(raw_key):
        raise AuthenticationError("API key is invalid.")
    if not is_api_key_usable(record):
        raise AuthenticationError("API key is expired or revoked.")
    return AuthenticationResult(subject=record.key_id, method="api_key")
