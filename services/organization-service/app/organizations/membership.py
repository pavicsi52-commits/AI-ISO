"""Membership-role ranking -- a pure function.

Per docs/033 "SECURITY": "Strict tenant isolation," "Validate
organization ownership," "Prevent cross-tenant access." This service's
own :class:`~app.models.member.OrganizationMember.role` (owner/admin/
member) is the self-contained enforcement mechanism for its own admin
endpoints -- see ``app/api/deps.py``'s ``require_org_role`` for how
it's used as a FastAPI dependency. Deeper integration with
``services/rbac-service`` (docs/033's own "Integrate Prompt 032") for
fine-grained, resource-level permission checks on organization-owned
data is a documented follow-up integration point, not built here --
see the package README's "Design decisions."
"""

from __future__ import annotations

from app.models.enums import MemberRole

_RANK: dict[MemberRole, int] = {
    MemberRole.MEMBER: 0,
    MemberRole.ADMIN: 1,
    MemberRole.OWNER: 2,
}


def role_at_least(role: MemberRole, minimum: MemberRole) -> bool:
    """Whether *role* meets or exceeds *minimum* in privilege (member < admin < owner)."""
    return _RANK[role] >= _RANK[minimum]


__all__ = ["role_at_least"]
