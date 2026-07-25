"""Role hierarchy algorithms: inheritance, aggregation, cycle detection.

Per docs/032 "ROLE HIERARCHY": Inheritance, Parent Roles, Child Roles,
Permission Aggregation, Recursive Evaluation, Circular Dependency
Detection. Pure functions operating on an in-memory role graph handed
in by the caller (mirroring ``shared_core.security.roles``'
pure-function style) -- no database access here, so
:class:`app.services.role.RoleService` can unit-test the algorithm
itself independent of persistence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID


class CircularRoleHierarchyError(Exception):
    """Raised when assigning ``parent_role_id`` would create a cycle."""

    def __init__(self, role_id: UUID, parent_role_id: UUID) -> None:
        self.role_id = role_id
        self.parent_role_id = parent_role_id
        super().__init__(
            f"Setting role {role_id}'s parent to {parent_role_id} would create a "
            "circular role hierarchy."
        )


@dataclass(frozen=True, slots=True)
class RoleNode:
    """The minimal shape :mod:`app.roles.hierarchy` needs for one role."""

    id: UUID
    parent_role_id: UUID | None


def would_create_cycle(roles: Mapping[UUID, RoleNode], role_id: UUID, new_parent_id: UUID) -> bool:
    """Whether setting *role_id*'s parent to *new_parent_id* creates a cycle.

    True if *role_id* itself, or a would-be descendant of *role_id*
    (impossible to check without walking down, so instead this walks
    *up* from *new_parent_id*: if *role_id* is found among
    *new_parent_id*'s own ancestors, the assignment would close a loop).
    """
    if new_parent_id == role_id:
        return True
    visited: set[UUID] = set()
    current: UUID | None = new_parent_id
    while current is not None:
        if current == role_id:
            return True
        if current in visited:
            return True  # an existing cycle elsewhere in the graph
        visited.add(current)
        node = roles.get(current)
        current = node.parent_role_id if node is not None else None
    return False


def resolve_ancestor_chain(roles: Mapping[UUID, RoleNode], role_id: UUID) -> list[UUID]:
    """*role_id*'s ancestors, nearest first, walking ``parent_role_id`` links.

    Stops (rather than looping forever) if a cycle is encountered, since
    a persisted cycle should never happen once :func:`would_create_cycle`
    is enforced on every write -- this is a defensive backstop, not the
    primary guard.
    """
    chain: list[UUID] = []
    visited: set[UUID] = set()
    node = roles.get(role_id)
    current = node.parent_role_id if node is not None else None
    while current is not None and current not in visited:
        chain.append(current)
        visited.add(current)
        node = roles.get(current)
        current = node.parent_role_id if node is not None else None
    return chain


def aggregate_permission_ids(
    roles: Mapping[UUID, RoleNode],
    role_permission_ids: Mapping[UUID, Sequence[UUID]],
    role_id: UUID,
) -> set[UUID]:
    """Every permission id granted to *role_id* directly, plus every permission
    id inherited from its ancestor chain ("Permission Aggregation").
    """
    aggregated: set[UUID] = set(role_permission_ids.get(role_id, ()))
    for ancestor_id in resolve_ancestor_chain(roles, role_id):
        aggregated.update(role_permission_ids.get(ancestor_id, ()))
    return aggregated


__all__ = [
    "CircularRoleHierarchyError",
    "RoleNode",
    "aggregate_permission_ids",
    "resolve_ancestor_chain",
    "would_create_cycle",
]
