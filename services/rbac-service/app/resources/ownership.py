"""Resource-instance authorization decisions.

Per docs/032 "RESOURCE AUTHORIZATION": Resource Owner, Organization
Scope, Project Scope, Shared Resources, Public Resources, Private
Resources, Inherited Permissions. A pure function over the
:class:`~app.models.resource_permission.ResourcePermission` rows
already fetched for one resource instance -- no database access here,
mirroring :mod:`app.roles.hierarchy`'s pure-function style, and
analogous in spirit to
:func:`shared_core.security.permissions.can_access_resource`'s
ownership override, but operating on this service's own persisted
grants instead of a single ``resource_owner_id`` parameter.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.models.enums import PolicyEffect, SubjectType
from app.models.resource_permission import ResourcePermission


@dataclass(frozen=True, slots=True)
class ResourceDecision:
    """The outcome of checking direct resource-instance grants."""

    decided: bool
    """Whether any direct grant/deny/ownership/public rule applied at all --
    ``False`` means "fall through to the role/policy-based decision."""
    allowed: bool = False
    reason: str = ""


def resolve_resource_decision(
    grants: list[ResourcePermission],
    *,
    permission_id: UUID,
    user_id: UUID,
    user_role_ids: set[UUID],
) -> ResourceDecision:
    """Resolve *user_id*'s direct access to one resource instance for
    *permission_id*, given every :class:`ResourcePermission` row recorded on it.

    Precedence (most to least specific): an explicit deny for this user
    always wins; then an explicit grant to this user, their role, or
    ownership; then a public grant. No matching row means "not decided
    here" -- the caller falls back to role/policy evaluation.
    """
    relevant = [g for g in grants if g.permission_id == permission_id]

    for grant in relevant:
        if grant.effect == PolicyEffect.DENY and _applies_to(grant, user_id, user_role_ids):
            return ResourceDecision(decided=True, allowed=False, reason="Explicitly denied.")

    for grant in relevant:
        if grant.effect != PolicyEffect.ALLOW:
            continue
        owns_it = grant.subject_type == SubjectType.USER and grant.subject_id == user_id
        if grant.is_owner and owns_it:
            return ResourceDecision(decided=True, allowed=True, reason="Resource owner.")
        if _applies_to(grant, user_id, user_role_ids):
            return ResourceDecision(decided=True, allowed=True, reason="Directly granted.")

    for grant in relevant:
        if grant.effect == PolicyEffect.ALLOW and grant.is_public:
            return ResourceDecision(decided=True, allowed=True, reason="Public resource.")

    return ResourceDecision(decided=False)


def _applies_to(grant: ResourcePermission, user_id: UUID, user_role_ids: set[UUID]) -> bool:
    if grant.subject_type == SubjectType.USER:
        return grant.subject_id == user_id
    if grant.subject_type == SubjectType.ROLE:
        return grant.subject_id in user_role_ids
    return False


__all__ = ["ResourceDecision", "resolve_resource_decision"]
