"""Tests for the request-scoped security context."""

from __future__ import annotations

from uuid import uuid4

from shared_core.enums import Role
from shared_core.security.context import (
    bind_security_context,
    get_security_context,
    reset_security_context,
)


def test_default_context_is_empty() -> None:
    reset_security_context()

    context = get_security_context()

    assert context.user_id is None
    assert context.role is None


def test_bind_security_context_merges_fields() -> None:
    reset_security_context()
    user_id = uuid4()

    bind_security_context(user_id=user_id, role=Role.OPERATOR)

    context = get_security_context()
    assert context.user_id == user_id
    assert context.role == Role.OPERATOR

    reset_security_context()


def test_bind_security_context_is_additive() -> None:
    reset_security_context()
    org_id = uuid4()

    bind_security_context(role=Role.VIEWER)
    bind_security_context(organization_id=org_id)

    context = get_security_context()
    assert context.role == Role.VIEWER
    assert context.organization_id == org_id

    reset_security_context()


def test_reset_security_context_clears_everything() -> None:
    bind_security_context(role=Role.VIEWER)
    reset_security_context()

    assert get_security_context().role is None
