"""JWT encode/decode, with key rotation and revocation support.

RS256 and ES256 only, per docs/017_Enterprise_Security_Framework.md.txt
"JWT": "Never HS256 for production." Clock skew is tolerated via a fixed
leeway; token revocation is checked via a caller-supplied predicate (this
package has no opinion on *where* revoked token IDs are stored -- that's
a session/cache concern, see :mod:`shared_core.security.sessions`).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt as pyjwt

from shared_core.constants.authentication import AuthConstants
from shared_core.exceptions.authentication import AuthenticationError

SUPPORTED_ALGORITHMS: tuple[str, ...] = ("RS256", "ES256")
CLOCK_SKEW_LEEWAY_SECONDS = 30


def encode_token(
    claims: dict[str, Any],
    *,
    private_key: str,
    algorithm: str = AuthConstants.JWT_ALGORITHM,
    ttl_seconds: int = AuthConstants.ACCESS_TOKEN_TTL_SECONDS,
    issuer: str = AuthConstants.JWT_ISSUER,
    key_id: str | None = None,
) -> str:
    """Encode a JWT signed with RS256 or ES256.

    Args:
        claims: Custom claims to embed (e.g. ``sub``, ``org_id``). A
            ``jti`` (JWT ID) is auto-generated if not already present,
            for revocation tracking.
        private_key: PEM-encoded RSA (RS256) or EC (ES256) private key.
        algorithm: ``"RS256"`` or ``"ES256"``.
        ttl_seconds: Token lifetime in seconds.
        issuer: Value of the ``iss`` claim.
        key_id: If given, set as the ``kid`` header so a
            :class:`KeyRing` can select the matching public key during
            verification (supports zero-downtime key rotation).

    Raises:
        AuthenticationError: If *algorithm* isn't RS256 or ES256.
    """
    if algorithm not in SUPPORTED_ALGORITHMS:
        raise AuthenticationError(
            f"Unsupported JWT algorithm '{algorithm}'. Use one of {SUPPORTED_ALGORITHMS}."
        )
    now = datetime.now(UTC)
    payload = {
        **claims,
        "iss": issuer,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
        "jti": claims.get("jti", str(uuid.uuid4())),
    }
    headers = {"kid": key_id} if key_id else None
    return pyjwt.encode(payload, private_key, algorithm=algorithm, headers=headers)


def decode_token(
    token: str,
    *,
    public_key: str,
    issuer: str = AuthConstants.JWT_ISSUER,
    is_revoked: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    """Decode and verify a JWT signed with RS256 or ES256.

    Args:
        token: The encoded JWT.
        public_key: PEM-encoded public key matching the signing key.
        issuer: Expected ``iss`` claim.
        is_revoked: Optional predicate checking the token's ``jti``
            against a revocation store.

    Raises:
        AuthenticationError: If the token is expired, malformed, the
            signature doesn't verify, or *is_revoked* returns ``True``.
    """
    try:
        claims: dict[str, Any] = pyjwt.decode(
            token,
            public_key,
            algorithms=list(SUPPORTED_ALGORITHMS),
            issuer=issuer,
            leeway=CLOCK_SKEW_LEEWAY_SECONDS,
        )
    except pyjwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired.") from exc
    except pyjwt.InvalidTokenError as exc:
        raise AuthenticationError("Token is invalid.") from exc

    if is_revoked is not None and is_revoked(claims.get("jti", "")):
        raise AuthenticationError("Token has been revoked.")

    return claims


def get_key_id(token: str) -> str | None:
    """Return the ``kid`` header of a JWT without verifying its signature.

    Used to select the correct public key when multiple keys are active
    during a rotation window.
    """
    header: dict[str, Any] = pyjwt.get_unverified_header(token)
    return header.get("kid")


class KeyRing:
    """A set of active public keys, keyed by ``kid``.

    During a key-rotation window, both the old and new public keys are
    registered here; :meth:`decode_with_ring` picks the right one per
    token based on its ``kid`` header, so in-flight tokens signed with the
    old key keep verifying until they naturally expire.
    """

    def __init__(self) -> None:
        self._keys: dict[str, str] = {}

    def add_key(self, key_id: str, public_key: str) -> None:
        """Register a public key under *key_id*."""
        self._keys[key_id] = public_key

    def remove_key(self, key_id: str) -> None:
        """Remove a public key, e.g. once its rotation grace period has ended."""
        self._keys.pop(key_id, None)

    def get_key(self, key_id: str) -> str | None:
        """Return the registered public key for *key_id*, if any."""
        return self._keys.get(key_id)

    def decode_with_ring(self, token: str, **kwargs: Any) -> dict[str, Any]:
        """Decode *token*, resolving its public key from this ring by ``kid``.

        Raises:
            AuthenticationError: If the token has no ``kid`` header, or
                no key is registered for it.
        """
        key_id = get_key_id(token)
        public_key = self.get_key(key_id) if key_id else None
        if public_key is None:
            raise AuthenticationError("No matching signing key found for token.")
        return decode_token(token, public_key=public_key, **kwargs)
