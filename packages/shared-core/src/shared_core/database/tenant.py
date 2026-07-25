"""Tenant isolation.

Per docs/018_Enterprise_Database_Framework.md.txt "TENANT ISOLATION": every
query automatically filters by Organization and Project; "Prevent Cross
Tenant Access"; "No bypass unless Super Admin."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import Select

from shared_core.database.exceptions import TenantViolationError
from shared_core.enums.role import Role
from shared_core.security.context import SecurityContext, get_security_context


@dataclass(frozen=True, slots=True)
class TenantScope:
    """The tenant boundary a repository (or query) is confined to.

    Passed to :class:`shared_core.database.repository.BaseRepository` so
    every query it builds is automatically tenant-filtered -- the
    "automatic" half of "TENANT ISOLATION"; a repository built without a
    scope is intentionally unscoped (e.g. platform-internal, cross-tenant
    tooling), never accidentally scoped.
    """

    organization_id: UUID | None
    project_id: UUID | None = None
    is_super_admin: bool = False

    @classmethod
    def from_security_context(cls, context: SecurityContext | None = None) -> TenantScope:
        """Build a :class:`TenantScope` from the current request's :class:`SecurityContext`."""
        ctx = context or get_security_context()
        return cls(
            organization_id=ctx.organization_id,
            project_id=ctx.project_id,
            is_super_admin=ctx.role == Role.SUPER_ADMIN,
        )


def apply_tenant_scope(
    stmt: Select[Any],
    model: type[Any],
    *,
    organization_id: UUID | None,
    project_id: UUID | None = None,
    is_super_admin: bool = False,
) -> Select[Any]:
    """Filter *stmt* to the given tenant scope, unless *is_super_admin*.

    Raises:
        TenantViolationError: If the caller is not a super admin and no
            *organization_id* was given -- an unscoped query is never
            allowed to silently see every tenant's data.
    """
    if is_super_admin:
        return stmt
    if organization_id is None:
        raise TenantViolationError("A tenant-scoped query requires an organization_id.")
    stmt = stmt.where(model.organization_id == organization_id)
    if project_id is not None:
        stmt = stmt.where(model.project_id == project_id)
    return stmt


def enforce_tenant_match(
    entity: Any,
    *,
    organization_id: UUID | None,
    project_id: UUID | None = None,
    is_super_admin: bool = False,
) -> None:
    """Raise :class:`TenantViolationError` if *entity* isn't in the given tenant scope.

    Defense in depth for entities fetched by primary key (which bypasses a
    ``WHERE organization_id = ...`` filter entirely) -- call after
    :meth:`~shared_core.database.repository.BaseRepository.get_by_id` and
    before returning the entity to the caller.
    """
    if is_super_admin:
        return
    if organization_id is None or entity.organization_id != organization_id:
        raise TenantViolationError(
            f"{type(entity).__name__} does not belong to the caller's organization."
        )
    if project_id is not None and entity.project_id is not None and entity.project_id != project_id:
        raise TenantViolationError(
            f"{type(entity).__name__} does not belong to the caller's project."
        )


def tenant_scope_from_security_context(
    context: SecurityContext | None = None,
) -> tuple[UUID | None, UUID | None, bool]:
    """Resolve ``(organization_id, project_id, is_super_admin)`` from the request context.

    Prefer :meth:`TenantScope.from_security_context` for new code -- this
    tuple form exists for callers that want the three values unpacked
    directly rather than as an object.
    """
    ctx = context or get_security_context()
    return ctx.organization_id, ctx.project_id, ctx.role == Role.SUPER_ADMIN


__all__ = [
    "TenantScope",
    "apply_tenant_scope",
    "enforce_tenant_match",
    "tenant_scope_from_security_context",
]
