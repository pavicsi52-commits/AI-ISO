"""Token issuance, rotation, and revocation.

Per docs/030 "JWT": Access Token, Refresh Token, Token Rotation, Token
Revocation, Token Blacklist, Token Validation. Wraps
:mod:`shared_core.security.jwt`/:mod:`shared_core.security.refresh`
(cryptography and claim shape) with this service's own DB-backed
``jti`` tracking for revocation and audit -- those modules explicitly
own no storage, per Prompt 017's own scope statement.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.constants.authentication import AuthConstants
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.helpers.hash_helper import sha256_hex
from shared_core.security.jwt import decode_token, encode_token
from shared_core.security.refresh import TokenPair

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.token import AccessToken, RefreshToken
from app.repositories.token import AccessTokenRepository, RefreshTokenRepository

_REFRESH_TOKEN_TYPE = "refresh"
_NON_CARRIED_CLAIMS = frozenset({"iss", "iat", "exp", "jti", "token_type"})


class TokenService:
    """Issues, validates, rotates, and revokes JWT access/refresh token pairs."""

    def __init__(
        self,
        access_tokens: AccessTokenRepository,
        refresh_tokens: RefreshTokenRepository,
        *,
        private_key: str,
        public_key: str,
        algorithm: str = AuthConstants.JWT_ALGORITHM,
        access_ttl_seconds: int = AuthConstants.ACCESS_TOKEN_TTL_SECONDS,
        refresh_ttl_seconds: int = AuthConstants.REFRESH_TOKEN_TTL_SECONDS,
    ) -> None:
        self._access_tokens = access_tokens
        self._refresh_tokens = refresh_tokens
        self._private_key = private_key
        self._public_key = public_key
        self._algorithm = algorithm
        self._access_ttl_seconds = access_ttl_seconds
        self._refresh_ttl_seconds = refresh_ttl_seconds

    async def issue(
        self,
        user_id: UUID,
        *,
        session_id: UUID | None = None,
        extra_claims: dict[str, Any] | None = None,
    ) -> TokenPair:
        """Issue a fresh access/refresh token pair for *user_id* ("Token Creation")."""
        claims = {"sub": str(user_id), **(extra_claims or {})}
        access_token = encode_token(
            claims,
            private_key=self._private_key,
            algorithm=self._algorithm,
            ttl_seconds=self._access_ttl_seconds,
        )
        refresh_token = encode_token(
            {**claims, "token_type": _REFRESH_TOKEN_TYPE},
            private_key=self._private_key,
            algorithm=self._algorithm,
            ttl_seconds=self._refresh_ttl_seconds,
        )
        pair = TokenPair(access_token=access_token, refresh_token=refresh_token)
        await self._track(pair, user_id=user_id, session_id=session_id)
        return pair

    async def refresh(self, refresh_token: str, *, session_id: UUID | None = None) -> TokenPair:
        """Verify *refresh_token*, rotate it, and issue a brand-new pair ("Token Rotation").

        Raises:
            AuthenticationError: If the token is invalid, expired,
                revoked, or isn't a refresh token.
        """
        claims = decode_token(refresh_token, public_key=self._public_key)
        if claims.get("token_type") != _REFRESH_TOKEN_TYPE:
            raise AuthenticationError("Token is not a refresh token.")

        old_jti = str(claims.get("jti", ""))
        record = await self._refresh_tokens.get_by_jti(old_jti)
        if record is None or record.revoked_at is not None:
            raise AuthenticationError("Refresh token has been revoked.")

        user_id = UUID(str(claims["sub"]))
        carried = {k: v for k, v in claims.items() if k not in _NON_CARRIED_CLAIMS}
        pair = await self.issue(user_id, session_id=session_id, extra_claims=carried)

        new_claims = decode_token(pair.refresh_token, public_key=self._public_key)
        record.revoked_at = datetime.now(UTC)
        record.replaced_by_jti = str(new_claims["jti"])
        return pair

    async def decode_access_token(self, access_token: str) -> dict[str, Any]:
        """Verify *access_token* and confirm it hasn't been revoked ("Token Validation").

        Raises:
            AuthenticationError: If the token is invalid, expired, or revoked.
        """
        claims = decode_token(access_token, public_key=self._public_key)
        jti = str(claims.get("jti", ""))
        record = await self._access_tokens.get_by_jti(jti)
        if record is not None and record.revoked_at is not None:
            raise AuthenticationError("Token has been revoked.")
        return claims

    async def decode_refresh_token(self, refresh_token: str) -> dict[str, Any]:
        """Verify *refresh_token* and confirm it hasn't been revoked.

        Raises:
            AuthenticationError: If the token is invalid, expired,
                revoked, or isn't a refresh token.
        """
        claims = decode_token(refresh_token, public_key=self._public_key)
        if claims.get("token_type") != _REFRESH_TOKEN_TYPE:
            raise AuthenticationError("Token is not a refresh token.")
        jti = str(claims.get("jti", ""))
        record = await self._refresh_tokens.get_by_jti(jti)
        if record is not None and record.revoked_at is not None:
            raise AuthenticationError("Token has been revoked.")
        return claims

    async def revoke_access_token(self, jti: str) -> None:
        """Mark an access token revoked ("Token Blacklist"/"Token Revocation")."""
        record = await self._access_tokens.get_by_jti(jti)
        if record is not None and record.revoked_at is None:
            record.revoked_at = datetime.now(UTC)

    async def revoke_refresh_token(self, jti: str) -> UUID | None:
        """Mark a refresh token revoked, returning its tracked session id, if any.

        Covers "Token Revocation".
        """
        record = await self._refresh_tokens.get_by_jti(jti)
        if record is None:
            return None
        if record.revoked_at is None:
            record.revoked_at = datetime.now(UTC)
        return record.session_id

    async def _track(self, pair: TokenPair, *, user_id: UUID, session_id: UUID | None) -> None:
        now = datetime.now(UTC)
        access_claims = decode_token(pair.access_token, public_key=self._public_key)
        refresh_claims = decode_token(pair.refresh_token, public_key=self._public_key)
        await self._access_tokens.create(
            AccessToken(
                user_id=user_id,
                session_id=session_id,
                jti=str(access_claims["jti"]),
                issued_at=now,
                expires_at=datetime.fromtimestamp(access_claims["exp"], tz=UTC),
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )
        await self._refresh_tokens.create(
            RefreshToken(
                user_id=user_id,
                session_id=session_id,
                jti=str(refresh_claims["jti"]),
                token_hash=sha256_hex(pair.refresh_token),
                issued_at=now,
                expires_at=datetime.fromtimestamp(refresh_claims["exp"], tz=UTC),
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )


__all__ = ["TokenService"]
