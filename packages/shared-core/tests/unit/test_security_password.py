"""Tests for the expanded password package: policy checks, breach checking."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from shared_core.security.password import (
    check_dictionary,
    check_password_expired,
    check_password_history,
    hash_password,
    hibp_lookup_key,
    is_breached,
)


def test_check_password_history_fails_for_reused_password() -> None:
    previous = [hash_password("OldP@ssw0rd123")]

    result = check_password_history("OldP@ssw0rd123", previous_hashes=previous)

    assert result.valid is False
    assert "reused" in result.reasons[0] or "previously" in result.reasons[0]


def test_check_password_history_passes_for_new_password() -> None:
    previous = [hash_password("OldP@ssw0rd123")]

    result = check_password_history("NewP@ssw0rd456", previous_hashes=previous)

    assert result.valid is True


def test_check_password_history_passes_with_no_history() -> None:
    result = check_password_history("AnyP@ssw0rd123", previous_hashes=[])

    assert result.valid is True


def test_check_password_expired_fails_when_too_old() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    result = check_password_expired(
        last_changed_at=now - timedelta(days=100), max_age_days=90, now=now
    )

    assert result.valid is False


def test_check_password_expired_passes_when_recent() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    result = check_password_expired(
        last_changed_at=now - timedelta(days=10), max_age_days=90, now=now
    )

    assert result.valid is True


def test_check_dictionary_fails_for_common_password() -> None:
    result = check_dictionary("password123", banned_words=["password123", "letmein"])

    assert result.valid is False


def test_check_dictionary_is_case_insensitive() -> None:
    result = check_dictionary("PASSWORD123", banned_words=["password123"])

    assert result.valid is False


def test_check_dictionary_passes_for_uncommon_password() -> None:
    result = check_dictionary("Xk9$mQ2vLp", banned_words=["password123", "letmein"])

    assert result.valid is True


def test_hibp_lookup_key_returns_five_char_prefix() -> None:
    prefix, suffix = hibp_lookup_key("correcthorsebatterystaple")

    assert len(prefix) == 5
    assert len(suffix) == 35  # SHA-1 hex digest is 40 chars total


def test_hibp_lookup_key_is_deterministic() -> None:
    assert hibp_lookup_key("same-password") == hibp_lookup_key("same-password")


def test_is_breached_true_when_suffix_matches() -> None:
    _, suffix = hibp_lookup_key("known-breached-password")

    result = is_breached("known-breached-password", known_suffixes={suffix})

    assert result.valid is False


def test_is_breached_false_when_suffix_does_not_match() -> None:
    result = is_breached("some-safe-password", known_suffixes={"nonmatching-suffix"})

    assert result.valid is True
