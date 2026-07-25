"""Tests for :mod:`app.rotation.policy` -- pure rotation-due evaluation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.rotation.policy import RotationPolicy, is_rotation_due, next_rotation_at


def test_from_json_defaults_to_disabled() -> None:
    policy = RotationPolicy.from_json({})
    assert policy.enabled is False
    assert policy.interval_days == 90


def test_from_json_parses_valid_fields() -> None:
    policy = RotationPolicy.from_json({"enabled": True, "interval_days": 30})
    assert policy.enabled is True
    assert policy.interval_days == 30


def test_from_json_falls_back_on_invalid_interval() -> None:
    policy = RotationPolicy.from_json({"enabled": True, "interval_days": -5})
    assert policy.interval_days == 90

    policy = RotationPolicy.from_json({"enabled": True, "interval_days": "not-a-number"})
    assert policy.interval_days == 90


def test_next_rotation_at_adds_interval() -> None:
    last_rotated = datetime(2026, 1, 1, tzinfo=UTC)
    policy = RotationPolicy(enabled=True, interval_days=30)
    assert next_rotation_at(policy, last_rotated_at=last_rotated) == last_rotated + timedelta(
        days=30
    )


def test_is_rotation_due_false_when_disabled() -> None:
    policy = RotationPolicy(enabled=False, interval_days=1)
    last_rotated = datetime(2020, 1, 1, tzinfo=UTC)
    assert is_rotation_due(policy, last_rotated_at=last_rotated, now=datetime.now(UTC)) is False


def test_is_rotation_due_true_when_interval_elapsed() -> None:
    policy = RotationPolicy(enabled=True, interval_days=30)
    now = datetime(2026, 6, 1, tzinfo=UTC)
    last_rotated = now - timedelta(days=31)
    assert is_rotation_due(policy, last_rotated_at=last_rotated, now=now) is True


def test_is_rotation_due_false_when_interval_not_elapsed() -> None:
    policy = RotationPolicy(enabled=True, interval_days=30)
    now = datetime(2026, 6, 1, tzinfo=UTC)
    last_rotated = now - timedelta(days=1)
    assert is_rotation_due(policy, last_rotated_at=last_rotated, now=now) is False
