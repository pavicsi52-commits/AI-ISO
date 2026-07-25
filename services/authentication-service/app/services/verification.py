"""Email verification.

Per docs/030 "EMAIL VERIFICATION": Generate Verification Token,
Expiration, Resend, Verification Status, Audit.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from shared_core.exceptions.authentication import AuthenticationError
from shared_core.helpers.hash_helper import sha256_hex
from shared_core.security.apikey import generate_random_token

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.email_verification import EmailVerificationToken
from app.models.user import User
from app.repositories.verification import EmailVerificationTokenRepository

_TOKEN_TTL_HOURS = 24


class VerificationService:
    """Generates and validates email verification tokens."""

    def __init__(self, tokens: EmailVerificationTokenRepository) -> None:
        self._tokens = tokens

    async def create_token(self, user: User) -> str:
        """Generate a fresh verification token for *user*.

        Covers "Generate Verification Token"/"Resend".
        """
        raw_token = generate_random_token()
        await self._tokens.create(
            EmailVerificationToken(
                user_id=user.id,
                email=user.email,
                token_hash=sha256_hex(raw_token),
                expires_at=datetime.now(UTC) + timedelta(hours=_TOKEN_TTL_HOURS),
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )
        return raw_token

    async def consume(self, raw_token: str) -> EmailVerificationToken:
        """Validate and mark a token used, returning it ("Verification Status").

        Raises:
            AuthenticationError: If the token doesn't exist, is expired, or was already used.
        """
        record = await self._tokens.get_by_token_hash(sha256_hex(raw_token))
        if record is None or record.used_at is not None:
            raise AuthenticationError("Verification token is invalid or has already been used.")
        if record.expires_at <= datetime.now(UTC):
            raise AuthenticationError("Verification token has expired.")
        record.used_at = datetime.now(UTC)
        return record


__all__ = ["VerificationService"]
