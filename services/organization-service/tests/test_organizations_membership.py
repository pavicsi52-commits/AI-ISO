"""Tests for ``app/organizations/membership.py`` -- pure role-ranking logic."""

from __future__ import annotations

import pytest

from app.models.enums import MemberRole
from app.organizations.membership import role_at_least


@pytest.mark.parametrize(
    ("role", "minimum", "expected"),
    [
        (MemberRole.OWNER, MemberRole.OWNER, True),
        (MemberRole.OWNER, MemberRole.ADMIN, True),
        (MemberRole.OWNER, MemberRole.MEMBER, True),
        (MemberRole.ADMIN, MemberRole.OWNER, False),
        (MemberRole.ADMIN, MemberRole.ADMIN, True),
        (MemberRole.ADMIN, MemberRole.MEMBER, True),
        (MemberRole.MEMBER, MemberRole.OWNER, False),
        (MemberRole.MEMBER, MemberRole.ADMIN, False),
        (MemberRole.MEMBER, MemberRole.MEMBER, True),
    ],
)
def test_role_at_least(role: MemberRole, minimum: MemberRole, expected: bool) -> None:
    assert role_at_least(role, minimum) is expected
