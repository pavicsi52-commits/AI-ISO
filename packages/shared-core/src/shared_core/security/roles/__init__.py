"""Custom and inherited roles.

Per docs/017_Enterprise_Security_Framework.md.txt "RBAC": "Custom Roles,
Inherited Roles." The fixed system :class:`~shared_core.enums.Role`
values and their permission sets live in
:mod:`shared_core.security.rbac`; this module resolves a *custom* role
definition's effective permissions, including inheritance from a base
system role.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shared_core.enums.permission import Permission
from shared_core.enums.role import Role
from shared_core.security.rbac import ROLE_PERMISSIONS


@dataclass(frozen=True, slots=True)
class CustomRole:
    """An organization-defined role, optionally inheriting a base system role."""

    name: str
    inherits_from: Role | None = None
    additional_permissions: frozenset[Permission] = field(default_factory=frozenset)
    revoked_permissions: frozenset[Permission] = field(default_factory=frozenset)


def resolve_custom_role_permissions(role: CustomRole) -> frozenset[Permission]:
    """Compute a custom role's effective permission set.

    Starts from the inherited base role's permissions (if any), adds
    ``additional_permissions``, then subtracts ``revoked_permissions`` --
    letting an org grant a role "OPERATOR plus APPROVE, minus EXECUTE",
    for example.
    """
    base = (
        ROLE_PERMISSIONS.get(role.inherits_from, frozenset())
        if role.inherits_from is not None
        else frozenset()
    )
    return (base | role.additional_permissions) - role.revoked_permissions
