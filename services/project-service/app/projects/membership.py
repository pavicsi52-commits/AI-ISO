"""Membership-role ranking -- a pure function.

Per docs/034 "SECURITY": "Validate ... Project membership," "Role
permissions," "Prevent cross-project access." Unlike
``services/organization-service``'s own three-value ``MemberRole``
enum, this service's roles are a genuinely dynamic, persisted catalog
(:class:`~app.models.project_role.ProjectRole`, supporting "Custom
Roles" per docs/034's own "PROJECT ROLES" section) -- so hierarchy
comparison is a numeric ``rank`` comparison, not a fixed enum lookup
table, generalizing the same idea ``app/organizations/membership.py::
role_at_least()`` established one tenant level up.
"""

from __future__ import annotations


def rank_at_least(role_rank: int, minimum_rank: int) -> bool:
    """Whether *role_rank* meets or exceeds *minimum_rank* in privilege."""
    return role_rank >= minimum_rank


__all__ = ["rank_at_least"]
