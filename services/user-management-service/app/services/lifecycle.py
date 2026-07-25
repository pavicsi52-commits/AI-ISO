"""User status lifecycle.

Per docs/031 "USER STATUS": "Status transitions shall be validated."
``DELETED`` is terminal (a hard stop, not a resurrection path -- a
service that wants a deleted user back creates a new one).
"""

from __future__ import annotations

from shared_core.exceptions.conflict import ConflictError

from app.models.enums import UserStatus

_VALID_TRANSITIONS: dict[UserStatus, frozenset[UserStatus]] = {
    UserStatus.PENDING: frozenset({UserStatus.INVITED, UserStatus.ACTIVE, UserStatus.DELETED}),
    UserStatus.INVITED: frozenset({UserStatus.ACTIVE, UserStatus.DELETED}),
    UserStatus.ACTIVE: frozenset(
        {
            UserStatus.INACTIVE,
            UserStatus.LOCKED,
            UserStatus.DISABLED,
            UserStatus.SUSPENDED,
            UserStatus.ARCHIVED,
            UserStatus.DELETED,
        }
    ),
    UserStatus.INACTIVE: frozenset({UserStatus.ACTIVE, UserStatus.ARCHIVED, UserStatus.DELETED}),
    UserStatus.LOCKED: frozenset({UserStatus.ACTIVE, UserStatus.DISABLED, UserStatus.DELETED}),
    UserStatus.DISABLED: frozenset({UserStatus.ACTIVE, UserStatus.DELETED}),
    UserStatus.SUSPENDED: frozenset({UserStatus.ACTIVE, UserStatus.DISABLED, UserStatus.DELETED}),
    UserStatus.ARCHIVED: frozenset({UserStatus.ACTIVE, UserStatus.DELETED}),
    UserStatus.DELETED: frozenset(),
}

#: Which target statuses count as "active" for UserActivated/UserDeactivated ("USER ACTIVITY").
ACTIVE_STATUS = UserStatus.ACTIVE


def is_valid_transition(current: UserStatus, target: UserStatus) -> bool:
    """Whether transitioning from *current* to *target* is a legal status change."""
    if current == target:
        return True
    return target in _VALID_TRANSITIONS.get(current, frozenset())


def validate_transition(current: UserStatus, target: UserStatus) -> None:
    """Raise unless transitioning from *current* to *target* is legal.

    Raises:
        ConflictError: If the transition isn't allowed.
    """
    if not is_valid_transition(current, target):
        raise ConflictError(f"Cannot transition user status from {current!r} to {target!r}.")


__all__ = ["ACTIVE_STATUS", "is_valid_transition", "validate_transition"]
