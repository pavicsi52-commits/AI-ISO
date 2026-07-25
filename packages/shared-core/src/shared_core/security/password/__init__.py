"""Password hashing and policy enforcement.

Argon2 hashing per docs/003_Technology_Stack_Master.md.txt. Character-
class/length rules already live in
:func:`shared_core.validators.fields.credentials.validate_password`
(Prompt 012) -- this module covers what that one doesn't: history, reuse
prevention, expiration, dictionary checks, and breach checking. Never
imports :mod:`shared_core.validation` (Prompt 016 already depends on
:mod:`shared_core.security`, so the reverse import would cycle).
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password. Never store plaintext passwords."""
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2 hash."""
    try:
        return _hasher.verify(hashed_password, plain_password)
    except VerifyMismatchError:
        return False


def needs_rehash(hashed_password: str) -> bool:
    """Return whether a hash was created with outdated Argon2 parameters."""
    return _hasher.check_needs_rehash(hashed_password)


@dataclass(frozen=True, slots=True)
class PasswordPolicyResult:
    """Outcome of a password policy check."""

    valid: bool
    reasons: list[str] = field(default_factory=list)

    @classmethod
    def ok(cls) -> PasswordPolicyResult:
        return cls(valid=True, reasons=[])

    @classmethod
    def fail(cls, *reasons: str) -> PasswordPolicyResult:
        return cls(valid=False, reasons=list(reasons))


def check_password_history(
    candidate: str, *, previous_hashes: Sequence[str]
) -> PasswordPolicyResult:
    """Reject a candidate password that matches any previously-used password."""
    if any(verify_password(candidate, previous_hash) for previous_hash in previous_hashes):
        return PasswordPolicyResult.fail("Password was used previously and cannot be reused.")
    return PasswordPolicyResult.ok()


def check_password_expired(
    *, last_changed_at: datetime, max_age_days: int, now: datetime | None = None
) -> PasswordPolicyResult:
    """Check whether a password has exceeded its maximum age."""
    current = now or datetime.now(UTC)
    if (current - last_changed_at) > timedelta(days=max_age_days):
        return PasswordPolicyResult.fail(
            f"Password has not been changed in over {max_age_days} days and must be reset."
        )
    return PasswordPolicyResult.ok()


def check_dictionary(candidate: str, *, banned_words: Collection[str]) -> PasswordPolicyResult:
    """Reject a candidate that (case-insensitively) matches a banned/common password."""
    if candidate.lower() in {word.lower() for word in banned_words}:
        return PasswordPolicyResult.fail(
            "Password is too common. Choose something less predictable."
        )
    return PasswordPolicyResult.ok()


def hibp_lookup_key(password: str) -> tuple[str, str]:
    """Return the (prefix, suffix) SHA-1 k-anonymity lookup key for *password*.

    Implements the local half of the HaveIBeenPwned range-query protocol:
    a caller sends ``prefix`` to the breach-check API and receives a list
    of candidate suffixes back; no network call happens in this framework
    layer -- see :func:`is_breached`.
    """
    digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    return digest[:5], digest[5:]


def is_breached(password: str, *, known_suffixes: Collection[str]) -> PasswordPolicyResult:
    """Check *password* against breach-database suffixes already fetched by the caller."""
    _, suffix = hibp_lookup_key(password)
    if suffix in known_suffixes:
        return PasswordPolicyResult.fail(
            "Password has appeared in a known data breach and must not be used."
        )
    return PasswordPolicyResult.ok()
