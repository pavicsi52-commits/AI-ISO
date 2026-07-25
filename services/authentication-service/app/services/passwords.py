"""Password hashing, policy enforcement, reuse prevention, and reset tokens.

Per docs/030 "PASSWORD POLICY": Minimum Length, Complexity, Password
History, Password Expiration, Reuse Prevention, Argon2 Hashing. Per
"PASSWORD RESET": Generate Secure Reset Tokens, Expiration, Single Use.
Character-class/length rules live in
:func:`shared_core.validators.fields.credentials.validate_password`
(already enforced at the schema layer, :func:`app.schemas.auth
.validated_password`); this service covers what that doesn't: hashing,
history, reuse prevention, expiration, and reset tokens.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from shared_core.constants.authentication import AuthConstants
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.exceptions.validation import ValidationError
from shared_core.helpers.hash_helper import sha256_hex
from shared_core.security.apikey import generate_random_token
from shared_core.security.password import (
    check_password_expired,
    check_password_history,
    hash_password,
    needs_rehash,
    verify_password,
)

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.password import PasswordHistoryEntry, PasswordResetToken
from app.models.user import User
from app.repositories.password import PasswordHistoryRepository, PasswordResetTokenRepository

_RESET_TOKEN_TTL_HOURS = 1


class PasswordService:
    """Hashes passwords, enforces history/reuse/expiration policy, and manages reset tokens."""

    def __init__(
        self,
        history: PasswordHistoryRepository,
        reset_tokens: PasswordResetTokenRepository,
        *,
        history_size: int = AuthConstants.PASSWORD_HISTORY_SIZE,
        max_age_days: int | None = None,
    ) -> None:
        self._history = history
        self._reset_tokens = reset_tokens
        self._history_size = history_size
        self._max_age_days = max_age_days

    def hash(self, password: str) -> str:
        """Hash *password* with Argon2 ("Argon2 Hashing")."""
        return hash_password(password)

    def verify(self, password: str, hashed_password: str) -> bool:
        """Verify *password* against *hashed_password*."""
        return verify_password(password, hashed_password)

    def needs_rehash(self, hashed_password: str) -> bool:
        """Whether *hashed_password* was hashed with outdated Argon2 parameters."""
        return needs_rehash(hashed_password)

    def check_expired(self, *, last_changed_at: datetime) -> bool:
        """Whether a password last changed at *last_changed_at* has expired.

        Covers "Password Expiration".
        """
        if self._max_age_days is None:
            return False
        result = check_password_expired(
            last_changed_at=last_changed_at, max_age_days=self._max_age_days
        )
        return not result.valid

    async def require_not_reused(self, user_id: UUID, candidate_password: str) -> None:
        """Raise unless *candidate_password* doesn't match any of the user's recent passwords.

        Covers "Password History"/"Reuse Prevention".

        Raises:
            ValidationError: If *candidate_password* matches a recent password.
        """
        recent = await self._history.list_recent_for_user(user_id, limit=self._history_size)
        result = check_password_history(
            candidate_password, previous_hashes=[entry.hashed_password for entry in recent]
        )
        if not result.valid:
            raise ValidationError("; ".join(result.reasons))

    async def record(self, user_id: UUID, hashed_password: str) -> None:
        """Append *hashed_password* to *user_id*'s password history."""
        await self._history.create(
            PasswordHistoryEntry(
                user_id=user_id,
                hashed_password=hashed_password,
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )

    async def create_reset_token(self, user: User) -> str:
        """Generate a fresh, single-use password reset token for *user*.

        Covers "Generate Secure Reset Tokens".
        """
        raw_token = generate_random_token()
        await self._reset_tokens.create(
            PasswordResetToken(
                user_id=user.id,
                token_hash=sha256_hex(raw_token),
                expires_at=datetime.now(UTC) + timedelta(hours=_RESET_TOKEN_TTL_HOURS),
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )
        return raw_token

    async def consume_reset_token(self, raw_token: str) -> PasswordResetToken:
        """Validate and mark a reset token used, returning it ("Single Use").

        Raises:
            AuthenticationError: If the token doesn't exist, is expired, or was already used.
        """
        record = await self._reset_tokens.get_by_token_hash(sha256_hex(raw_token))
        if record is None or record.used_at is not None:
            raise AuthenticationError("Reset token is invalid or has already been used.")
        if record.expires_at <= datetime.now(UTC):
            raise AuthenticationError("Reset token has expired.")
        record.used_at = datetime.now(UTC)
        return record


__all__ = ["PasswordService"]
