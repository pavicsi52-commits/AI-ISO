"""Tests for :mod:`app.resources.ownership`'s pure resolution function."""

from __future__ import annotations

import uuid

from app.models.enums import PolicyEffect, ResourceType, SubjectType
from app.models.resource_permission import ResourcePermission
from app.resources.ownership import resolve_resource_decision


def _grant(**kwargs: object) -> ResourcePermission:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "resource_type": ResourceType.REPORTS,
        "resource_id": uuid.uuid4(),
        "subject_type": SubjectType.USER,
        "subject_id": uuid.uuid4(),
        "permission_id": uuid.uuid4(),
        "effect": PolicyEffect.ALLOW,
        "is_owner": False,
        "is_public": False,
    }
    defaults.update(kwargs)
    return ResourcePermission(**defaults)


def test_no_grants_returns_undecided() -> None:
    result = resolve_resource_decision(
        [], permission_id=uuid.uuid4(), user_id=uuid.uuid4(), user_role_ids=set()
    )

    assert result.decided is False


def test_owner_grant_allows() -> None:
    user_id = uuid.uuid4()
    permission_id = uuid.uuid4()
    grant = _grant(
        subject_type=SubjectType.USER,
        subject_id=user_id,
        permission_id=permission_id,
        is_owner=True,
    )

    result = resolve_resource_decision(
        [grant], permission_id=permission_id, user_id=user_id, user_role_ids=set()
    )

    assert result.decided is True
    assert result.allowed is True
    assert "owner" in result.reason.lower()


def test_direct_user_grant_allows() -> None:
    user_id = uuid.uuid4()
    permission_id = uuid.uuid4()
    grant = _grant(subject_type=SubjectType.USER, subject_id=user_id, permission_id=permission_id)

    result = resolve_resource_decision(
        [grant], permission_id=permission_id, user_id=user_id, user_role_ids=set()
    )

    assert result.decided is True
    assert result.allowed is True


def test_role_based_grant_allows() -> None:
    role_id = uuid.uuid4()
    permission_id = uuid.uuid4()
    grant = _grant(subject_type=SubjectType.ROLE, subject_id=role_id, permission_id=permission_id)

    result = resolve_resource_decision(
        [grant], permission_id=permission_id, user_id=uuid.uuid4(), user_role_ids={role_id}
    )

    assert result.decided is True
    assert result.allowed is True


def test_public_grant_allows_anyone() -> None:
    permission_id = uuid.uuid4()
    grant = _grant(
        subject_type=SubjectType.USER,
        subject_id=uuid.uuid4(),
        permission_id=permission_id,
        is_public=True,
    )

    result = resolve_resource_decision(
        [grant], permission_id=permission_id, user_id=uuid.uuid4(), user_role_ids=set()
    )

    assert result.decided is True
    assert result.allowed is True
    assert "public" in result.reason.lower()


def test_explicit_deny_wins_over_allow() -> None:
    user_id = uuid.uuid4()
    permission_id = uuid.uuid4()
    allow_grant = _grant(
        subject_type=SubjectType.USER, subject_id=user_id, permission_id=permission_id
    )
    deny_grant = _grant(
        subject_type=SubjectType.USER,
        subject_id=user_id,
        permission_id=permission_id,
        effect=PolicyEffect.DENY,
    )

    result = resolve_resource_decision(
        [allow_grant, deny_grant],
        permission_id=permission_id,
        user_id=user_id,
        user_role_ids=set(),
    )

    assert result.decided is True
    assert result.allowed is False


def test_grant_for_different_permission_is_ignored() -> None:
    user_id = uuid.uuid4()
    grant = _grant(subject_type=SubjectType.USER, subject_id=user_id, permission_id=uuid.uuid4())

    result = resolve_resource_decision(
        [grant], permission_id=uuid.uuid4(), user_id=user_id, user_role_ids=set()
    )

    assert result.decided is False


def test_deny_for_different_user_does_not_block_this_users_allow() -> None:
    user_id = uuid.uuid4()
    permission_id = uuid.uuid4()
    other_users_deny = _grant(
        subject_type=SubjectType.USER,
        subject_id=uuid.uuid4(),
        permission_id=permission_id,
        effect=PolicyEffect.DENY,
    )
    this_users_allow = _grant(
        subject_type=SubjectType.USER, subject_id=user_id, permission_id=permission_id
    )

    result = resolve_resource_decision(
        [other_users_deny, this_users_allow],
        permission_id=permission_id,
        user_id=user_id,
        user_role_ids=set(),
    )

    assert result.decided is True
    assert result.allowed is True


def test_grant_for_unrelated_subject_is_ignored() -> None:
    permission_id = uuid.uuid4()
    grant = _grant(
        subject_type=SubjectType.USER, subject_id=uuid.uuid4(), permission_id=permission_id
    )

    result = resolve_resource_decision(
        [grant], permission_id=permission_id, user_id=uuid.uuid4(), user_role_ids=set()
    )

    assert result.decided is False
