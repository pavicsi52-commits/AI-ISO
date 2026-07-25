"""Tests for :mod:`app.leasing.policy` -- pure lease expiration logic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.leasing.policy import compute_expiry, is_lease_expired


def test_compute_expiry_adds_duration() -> None:
    issued_at = datetime(2026, 1, 1, tzinfo=UTC)
    assert compute_expiry(issued_at=issued_at, duration_seconds=3600) == issued_at + timedelta(
        hours=1
    )


def test_is_lease_expired_false_before_expiry() -> None:
    expires_at = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    now = expires_at - timedelta(minutes=1)
    assert is_lease_expired(expires_at=expires_at, now=now) is False


def test_is_lease_expired_true_after_expiry() -> None:
    expires_at = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    now = expires_at + timedelta(minutes=1)
    assert is_lease_expired(expires_at=expires_at, now=now) is True


def test_is_lease_expired_true_at_exact_expiry() -> None:
    expires_at = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    assert is_lease_expired(expires_at=expires_at, now=expires_at) is True
