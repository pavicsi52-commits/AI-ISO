"""Tests for :mod:`app.roles.hierarchy`'s pure functions."""

from __future__ import annotations

import uuid

from app.roles.hierarchy import (
    CircularRoleHierarchyError,
    RoleNode,
    aggregate_permission_ids,
    resolve_ancestor_chain,
    would_create_cycle,
)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def test_would_create_cycle_detects_self_parent() -> None:
    role_id = _uuid()

    assert would_create_cycle({}, role_id, role_id) is True


def test_would_create_cycle_detects_indirect_cycle() -> None:
    a, b, c = _uuid(), _uuid(), _uuid()
    roles = {
        a: RoleNode(id=a, parent_role_id=None),
        b: RoleNode(id=b, parent_role_id=a),
        c: RoleNode(id=c, parent_role_id=b),
    }

    # Setting a's parent to c would close a -> c -> b -> a.
    assert would_create_cycle(roles, a, c) is True


def test_would_create_cycle_allows_valid_reparenting() -> None:
    a, b, c = _uuid(), _uuid(), _uuid()
    roles = {
        a: RoleNode(id=a, parent_role_id=None),
        b: RoleNode(id=b, parent_role_id=a),
        c: RoleNode(id=c, parent_role_id=None),
    }

    assert would_create_cycle(roles, b, c) is False


def test_resolve_ancestor_chain_walks_up() -> None:
    a, b, c = _uuid(), _uuid(), _uuid()
    roles = {
        a: RoleNode(id=a, parent_role_id=None),
        b: RoleNode(id=b, parent_role_id=a),
        c: RoleNode(id=c, parent_role_id=b),
    }

    assert resolve_ancestor_chain(roles, c) == [b, a]


def test_resolve_ancestor_chain_empty_for_root_role() -> None:
    a = _uuid()
    roles = {a: RoleNode(id=a, parent_role_id=None)}

    assert resolve_ancestor_chain(roles, a) == []


def test_resolve_ancestor_chain_stops_on_existing_cycle() -> None:
    a, b = _uuid(), _uuid()
    roles = {
        a: RoleNode(id=a, parent_role_id=b),
        b: RoleNode(id=b, parent_role_id=a),
    }

    chain = resolve_ancestor_chain(roles, a)

    assert set(chain) == {a, b}
    assert len(chain) == 2


def test_aggregate_permission_ids_includes_direct_and_inherited() -> None:
    parent, child = _uuid(), _uuid()
    perm_a, perm_b = _uuid(), _uuid()
    roles = {
        parent: RoleNode(id=parent, parent_role_id=None),
        child: RoleNode(id=child, parent_role_id=parent),
    }
    role_permission_ids = {parent: [perm_a], child: [perm_b]}

    aggregated = aggregate_permission_ids(roles, role_permission_ids, child)

    assert aggregated == {perm_a, perm_b}


def test_aggregate_permission_ids_role_with_no_grants() -> None:
    role_id = _uuid()
    roles = {role_id: RoleNode(id=role_id, parent_role_id=None)}

    assert aggregate_permission_ids(roles, {}, role_id) == set()


def test_circular_role_hierarchy_error_message() -> None:
    role_id, parent_id = _uuid(), _uuid()

    error = CircularRoleHierarchyError(role_id, parent_id)

    assert str(role_id) in str(error)
    assert str(parent_id) in str(error)
    assert error.role_id == role_id
    assert error.parent_role_id == parent_id
