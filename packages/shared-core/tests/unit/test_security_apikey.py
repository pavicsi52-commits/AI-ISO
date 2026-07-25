"""Tests for the API key lifecycle package."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from shared_core.security.apikey import (
    check_api_key_ip_allowed,
    check_api_key_scope,
    create_api_key,
    hash_api_key,
    is_api_key_expired,
    is_api_key_usable,
    record_api_key_usage,
    revoke_api_key,
    rotate_api_key,
)


def test_create_api_key_returns_raw_key_and_record() -> None:
    raw_key, record = create_api_key(scopes=["read"], ttl_days=30)

    assert raw_key.startswith("aiios_")
    assert record.hashed_key == hash_api_key(raw_key)
    assert record.scopes == frozenset({"read"})
    assert record.revoked is False


def test_create_api_key_without_ttl_never_expires() -> None:
    _, record = create_api_key()

    assert record.expires_at is None
    assert is_api_key_expired(record) is False


def test_is_api_key_expired_true_after_ttl() -> None:
    _, record = create_api_key(ttl_days=1)

    future = datetime.now(UTC) + timedelta(days=2)

    assert is_api_key_expired(record, now=future) is True


def test_is_api_key_expired_false_before_ttl() -> None:
    _, record = create_api_key(ttl_days=30)

    assert is_api_key_expired(record, now=datetime.now(UTC)) is False


def test_is_api_key_usable_false_when_revoked() -> None:
    _, record = create_api_key()
    revoked = revoke_api_key(record)

    assert is_api_key_usable(revoked) is False


def test_is_api_key_usable_true_for_fresh_key() -> None:
    _, record = create_api_key()

    assert is_api_key_usable(record) is True


def test_revoke_api_key_does_not_mutate_original() -> None:
    _, record = create_api_key()

    revoked = revoke_api_key(record)

    assert record.revoked is False
    assert revoked.revoked is True


def test_record_api_key_usage_sets_last_used_at() -> None:
    _, record = create_api_key()
    assert record.last_used_at is None

    used = record_api_key_usage(record)

    assert used.last_used_at is not None


def test_check_api_key_scope_passes_for_granted_scope() -> None:
    _, record = create_api_key(scopes=["read", "write"])

    assert check_api_key_scope(record, "read") is True


def test_check_api_key_scope_fails_for_ungranted_scope() -> None:
    _, record = create_api_key(scopes=["read"])

    assert check_api_key_scope(record, "delete") is False


def test_check_api_key_scope_empty_scopes_means_unrestricted() -> None:
    _, record = create_api_key(scopes=[])

    assert check_api_key_scope(record, "anything") is True


def test_check_api_key_ip_allowed_passes_for_listed_ip() -> None:
    _, record = create_api_key(ip_allowlist=["1.2.3.4"])

    assert check_api_key_ip_allowed(record, "1.2.3.4") is True


def test_check_api_key_ip_allowed_fails_for_unlisted_ip() -> None:
    _, record = create_api_key(ip_allowlist=["1.2.3.4"])

    assert check_api_key_ip_allowed(record, "5.6.7.8") is False


def test_check_api_key_ip_allowed_empty_allowlist_means_unrestricted() -> None:
    _, record = create_api_key(ip_allowlist=[])

    assert check_api_key_ip_allowed(record, "anything") is True


def test_rotate_api_key_issues_new_key_and_revokes_old() -> None:
    _, original = create_api_key(scopes=["read"], ttl_days=30)

    new_raw_key, new_record, revoked_old = rotate_api_key(original)

    assert new_raw_key.startswith("aiios_")
    assert new_record.key_id != original.key_id
    assert new_record.scopes == original.scopes
    assert revoked_old.revoked is True
    assert revoked_old.key_id == original.key_id


def test_rotate_api_key_preserves_no_ttl() -> None:
    _, original = create_api_key()  # no ttl

    _, new_record, _ = rotate_api_key(original)

    assert new_record.expires_at is None
