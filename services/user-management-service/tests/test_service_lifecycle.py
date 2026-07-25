"""Tests for :mod:`app.services.lifecycle`'s status transition validation."""

from __future__ import annotations

import pytest
from shared_core.exceptions.conflict import ConflictError

from app.models.enums import UserStatus
from app.services.lifecycle import is_valid_transition, validate_transition


@pytest.mark.parametrize(
    "current,target",
    [
        (UserStatus.PENDING, UserStatus.INVITED),
        (UserStatus.PENDING, UserStatus.ACTIVE),
        (UserStatus.INVITED, UserStatus.ACTIVE),
        (UserStatus.ACTIVE, UserStatus.INACTIVE),
        (UserStatus.ACTIVE, UserStatus.LOCKED),
        (UserStatus.ACTIVE, UserStatus.SUSPENDED),
        (UserStatus.LOCKED, UserStatus.ACTIVE),
        (UserStatus.SUSPENDED, UserStatus.ACTIVE),
        (UserStatus.INACTIVE, UserStatus.ARCHIVED),
        (UserStatus.ARCHIVED, UserStatus.ACTIVE),
        (UserStatus.ACTIVE, UserStatus.ACTIVE),
    ],
)
def test_valid_transitions(current: UserStatus, target: UserStatus) -> None:
    assert is_valid_transition(current, target) is True
    validate_transition(current, target)  # should not raise


@pytest.mark.parametrize(
    "current,target",
    [
        (UserStatus.DELETED, UserStatus.ACTIVE),
        (UserStatus.PENDING, UserStatus.SUSPENDED),
        (UserStatus.ARCHIVED, UserStatus.INACTIVE),
        (UserStatus.DISABLED, UserStatus.SUSPENDED),
    ],
)
def test_invalid_transitions(current: UserStatus, target: UserStatus) -> None:
    assert is_valid_transition(current, target) is False
    with pytest.raises(ConflictError):
        validate_transition(current, target)


def test_every_status_can_reach_deleted_except_deleted_itself() -> None:
    for status in UserStatus:
        if status is UserStatus.DELETED:
            continue
        assert is_valid_transition(status, UserStatus.DELETED) is True


def test_deleted_is_terminal() -> None:
    for status in UserStatus:
        if status is UserStatus.DELETED:
            continue
        assert is_valid_transition(UserStatus.DELETED, status) is False
