"""Refresh token lifecycle.

Per docs/017_Enterprise_Security_Framework.md.txt "JWT": "Refresh Token,
Token Rotation, Token Revocation." Paired with
:mod:`shared_core.security.jwt` (access tokens): a refresh token is a
long-lived JWT whose only job is to mint a new access/refresh token pair,
so it can be rotated (invalidate the old, issue a new) and revoked
independently of access tokens.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from shared_core.constants.authentication import AuthConstants
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.security.jwt import decode_token, encode_token

_NON_CARRIED_CLAIMS = frozenset({"iss", "iat", "exp", "jti", "token_type"})


@dataclass(frozen=True, slots=True)
class TokenPair:
    """A freshly issued access/refresh token pair."""

    access_token: str
    refresh_token: str


def issue_token_pair(
    claims: dict[str, Any],
    *,
    private_key: str,
    algorithm: str = AuthConstants.JWT_ALGORITHM,
    access_ttl_seconds: int = AuthConstants.ACCESS_TOKEN_TTL_SECONDS,
    refresh_ttl_seconds: int = AuthConstants.REFRESH_TOKEN_TTL_SECONDS,
) -> TokenPair:
    """Issue a fresh access/refresh token pair carrying the same claims."""
    access_token = encode_token(
        claims, private_key=private_key, algorithm=algorithm, ttl_seconds=access_ttl_seconds
    )
    refresh_token = encode_token(
        {**claims, "token_type": "refresh"},
        private_key=private_key,
        algorithm=algorithm,
        ttl_seconds=refresh_ttl_seconds,
    )
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


def rotate_token_pair(
    refresh_token: str,
    *,
    public_key: str,
    private_key: str,
    algorithm: str = AuthConstants.JWT_ALGORITHM,
    is_revoked: Callable[[str], bool] | None = None,
    access_ttl_seconds: int = AuthConstants.ACCESS_TOKEN_TTL_SECONDS,
    refresh_ttl_seconds: int = AuthConstants.REFRESH_TOKEN_TTL_SECONDS,
) -> TokenPair:
    """Verify *refresh_token*, then issue a brand-new access/refresh pair.

    Raises:
        AuthenticationError: If the refresh token is invalid, expired,
            revoked, or isn't actually a refresh token (an access token
            can't be used to refresh itself).
    """
    claims = decode_token(refresh_token, public_key=public_key, is_revoked=is_revoked)
    if claims.get("token_type") != "refresh":
        raise AuthenticationError("Token is not a refresh token.")
    carried_claims = {k: v for k, v in claims.items() if k not in _NON_CARRIED_CLAIMS}
    return issue_token_pair(
        carried_claims,
        private_key=private_key,
        algorithm=algorithm,
        access_ttl_seconds=access_ttl_seconds,
        refresh_ttl_seconds=refresh_ttl_seconds,
    )
