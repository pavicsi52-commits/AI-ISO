"""API key lifecycle: create, rotate, expire, revoke, scope, and IP-restrict.

Per docs/017_Enterprise_Security_Framework.md.txt "API KEYS": Create,
Rotate, Expire, Revoke, Scopes, Usage Tracking, Last Used, IP Restriction,
Rate Limit (rate limiting itself is
:mod:`shared_core.security.ratelimit`'s concern -- this module tracks the
key's identity and usage, not request throughput).

Renamed from the Prompt 012 baseline's ``tokens.py`` -- ``apikey`` is the
name docs/017's directory structure specifies.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Collection
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

from shared_core.constants.authentication import AuthConstants
from shared_core.helpers.hash_helper import sha256_hex


def generate_api_key() -> str:
    """Generate a new API key with the standard ``aiios_`` prefix."""
    token = secrets.token_urlsafe(AuthConstants.API_KEY_LENGTH)
    return f"{AuthConstants.API_KEY_PREFIX}{token}"


def generate_random_token(length_bytes: int = 32) -> str:
    """Generate a URL-safe random token, e.g. for password reset links."""
    return secrets.token_urlsafe(length_bytes)


def hash_api_key(api_key: str) -> str:
    """Return a SHA-256 hash of an API key for storage/lookup.

    API keys are hashed at rest (like passwords) so a database leak does
    not expose usable credentials.
    """
    return sha256_hex(api_key)


@dataclass(frozen=True, slots=True)
class ApiKeyRecord:
    """Everything about an API key *except* the raw key itself.

    The raw key is returned once, at creation/rotation time, and never
    stored -- only :attr:`hashed_key` is persisted, matching how
    passwords are handled.
    """

    key_id: str
    hashed_key: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    revoked: bool = False
    ip_allowlist: frozenset[str] = field(default_factory=frozenset)


def create_api_key(
    *,
    scopes: Collection[str] = (),
    ttl_days: int | None = None,
    ip_allowlist: Collection[str] = (),
) -> tuple[str, ApiKeyRecord]:
    """Create a new API key. Returns ``(raw_key, record)`` -- store only *record*."""
    raw_key = generate_api_key()
    now = datetime.now(UTC)
    record = ApiKeyRecord(
        key_id=str(uuid.uuid4()),
        hashed_key=hash_api_key(raw_key),
        scopes=frozenset(scopes),
        created_at=now,
        expires_at=now + timedelta(days=ttl_days) if ttl_days is not None else None,
        ip_allowlist=frozenset(ip_allowlist),
    )
    return raw_key, record


def rotate_api_key(record: ApiKeyRecord) -> tuple[str, ApiKeyRecord, ApiKeyRecord]:
    """Rotate an API key: issue a new one carrying over scopes/TTL/IP allowlist.

    Returns ``(new_raw_key, new_record, revoked_old_record)`` -- the
    caller persists both the new record and the now-revoked old one.
    """
    ttl_days: int | None = None
    if record.expires_at is not None:
        remaining = record.expires_at - record.created_at
        ttl_days = max(remaining.days, 0)
    new_raw_key, new_record = create_api_key(
        scopes=record.scopes, ttl_days=ttl_days, ip_allowlist=record.ip_allowlist
    )
    revoked_old_record = replace(record, revoked=True)
    return new_raw_key, new_record, revoked_old_record


def revoke_api_key(record: ApiKeyRecord) -> ApiKeyRecord:
    """Return a copy of *record* marked revoked."""
    return replace(record, revoked=True)


def record_api_key_usage(record: ApiKeyRecord, *, now: datetime | None = None) -> ApiKeyRecord:
    """Return a copy of *record* with ``last_used_at`` updated."""
    return replace(record, last_used_at=now or datetime.now(UTC))


def is_api_key_expired(record: ApiKeyRecord, *, now: datetime | None = None) -> bool:
    """Return whether *record* has passed its expiration time."""
    if record.expires_at is None:
        return False
    return (now or datetime.now(UTC)) >= record.expires_at


def is_api_key_usable(record: ApiKeyRecord, *, now: datetime | None = None) -> bool:
    """Return whether *record* is neither revoked nor expired."""
    return not record.revoked and not is_api_key_expired(record, now=now)


def check_api_key_scope(record: ApiKeyRecord, required_scope: str) -> bool:
    """Return whether *record* grants *required_scope*.

    An empty scope set means "all scopes" (an unscoped, full-access key).
    """
    return not record.scopes or required_scope in record.scopes


def check_api_key_ip_allowed(record: ApiKeyRecord, ip_address: str) -> bool:
    """Return whether *ip_address* is permitted to use *record*.

    An empty allowlist means "no IP restriction".
    """
    return not record.ip_allowlist or ip_address in record.ip_allowlist
