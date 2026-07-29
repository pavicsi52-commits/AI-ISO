"""Sharing, link, and permission endpoints.

``POST /dashboards/share`` is the path docs/048 names; the rest of the
sharing surface hangs off ``/dashboards/shares`` and
``/dashboards/permissions`` so the literal segments never collide with
``/dashboards/{dashboard_id}``.

**A token is returned by exactly one endpoint.** :func:`create_link`
hands the caller their new token; nothing else in this service ever
echoes one back, because a listing that included tokens would give
every viewer of the share list a working credential for every link.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from shared_core.exceptions.authorization import AuthorizationError
from shared_core.logging.context import get_log_context

from app.api.deps import (
    AuditSvc,
    CallerRoles,
    CurrentUserId,
    DashboardSvc,
    LinkDashboardSvc,
    NotificationSvc,
    SharingSvc,
)
from app.models.dashboard import Dashboard
from app.models.dashboard_share import DashboardShare
from app.models.enums import AuditAction, LayoutBreakpoint, SharePermission
from app.schemas.dashboard import (
    DashboardLoadResponse,
    DashboardSummary,
    GridResponse,
    ResolvedWidgetResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.sharing import (
    AccessResponse,
    RolePermissionRequest,
    RolePermissionSummary,
    ShareLinkRequest,
    ShareLinkResponse,
    ShareSummary,
    ShareWithUserRequest,
)

router = APIRouter(prefix="/dashboards", tags=["Sharing"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _summary(share: DashboardShare) -> ShareSummary:
    """Present one share, never its token."""
    summary = ShareSummary.model_validate(share)
    summary.is_link = share.share_token is not None
    return summary


async def _manageable(
    dashboard_id: UUID,
    *,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    audit: AuditSvc,
    caller: UUID,
    roles: list[str],
    action: AuditAction,
) -> Dashboard:
    """Load a dashboard the caller may share, auditing a refusal."""
    dashboard = await dashboards.get_by_id(dashboard_id)
    try:
        await sharing.require_access(
            dashboard, user_id=caller, roles=roles, need=SharePermission.MANAGE
        )
    except AuthorizationError as exc:
        await audit.record_denied(
            organization_id=dashboard.organization_id,
            action=action,
            entity_type="dashboard",
            entity_id=dashboard_id,
            actor_id=caller,
            reason=str(exc),
        )
        raise
    return dashboard


@router.post(
    "/share",
    response_model=SuccessResponse[ShareSummary],
    status_code=status.HTTP_201_CREATED,
    summary="Share a dashboard with a user",
)
async def share_dashboard(
    body: ShareWithUserRequest,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    audit: AuditSvc,
    notifications: NotificationSvc,
    caller: CurrentUserId,
    roles: CallerRoles,
) -> SuccessResponse[ShareSummary]:
    """Grant one person access to a dashboard."""
    dashboard = await _manageable(
        body.dashboard_id,
        dashboards=dashboards,
        sharing=sharing,
        audit=audit,
        caller=caller,
        roles=roles,
        action=AuditAction.DASHBOARD_SHARED,
    )
    share = await sharing.share_with_user(
        dashboard,
        user_id=body.user_id,
        permission=body.permission,
        shared_by=caller,
        expires_at=body.expires_at,
    )
    await notifications.send_dashboard_shared(
        str(body.user_id), name=dashboard.name, shared_by=str(caller)
    )
    await audit.record(
        organization_id=dashboard.organization_id,
        action=AuditAction.DASHBOARD_SHARED,
        entity_type="share",
        entity_id=share.id,
        actor_id=caller,
        context={"shared_with_user_id": str(body.user_id), "permission": str(body.permission)},
    )
    return SuccessResponse(message="Dashboard shared.", data=_summary(share), meta=_meta())


@router.post(
    "/share/link",
    response_model=SuccessResponse[ShareLinkResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Mint a read-only share link",
)
async def create_link(
    body: ShareLinkRequest,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
    roles: CallerRoles,
) -> SuccessResponse[ShareLinkResponse]:
    """Mint a time-limited read-only link.

    **The returned token is shown once.** It is a bearer credential for
    someone with no session; store it now, because no other endpoint
    will give it back.
    """
    dashboard = await _manageable(
        body.dashboard_id,
        dashboards=dashboards,
        sharing=sharing,
        audit=audit,
        caller=caller,
        roles=roles,
        action=AuditAction.DASHBOARD_SHARED,
    )
    share, token = await sharing.create_link(
        dashboard, shared_by=caller, ttl_seconds=body.ttl_seconds
    )
    await audit.record(
        organization_id=dashboard.organization_id,
        action=AuditAction.DASHBOARD_SHARED,
        entity_type="share",
        entity_id=share.id,
        actor_id=caller,
        context={"channel": "link"},
    )
    return SuccessResponse(
        message="Share link created. The token is shown once -- store it now.",
        data=ShareLinkResponse(share=_summary(share), token=token, expires_at=share.expires_at),
        meta=_meta(),
    )


@router.get(
    "/shared/{token}",
    response_model=SuccessResponse[DashboardLoadResponse],
    summary="Open a dashboard through a share link",
)
async def open_shared(
    token: str,
    dashboards: LinkDashboardSvc,
    sharing: SharingSvc,
    audit: AuditSvc,
    breakpoint_: Annotated[LayoutBreakpoint, Query(alias="breakpoint")] = (
        LayoutBreakpoint.DESKTOP
    ),
) -> SuccessResponse[DashboardLoadResponse]:
    """Resolve a share token and load its dashboard read-only.

    Genuinely reachable without a session: the token *is* the
    credential, which is the entire purpose of a share link. Revocation
    and expiry are enforced by :meth:`SharingService.resolve_link`,
    which is what makes the link time-limited rather than merely
    labelled so.

    **A signed-in visitor sees data; an anonymous one sees structure.**
    Widgets are resolved with the visitor's own token when they have
    one. Without a token every widget comes back ``UNAUTHORIZED`` --
    this service holds no credential of its own, and resolving under
    the *sharer's* rights would hand a stranger whatever that person
    can see. See :func:`app.api.deps.get_link_dashboard_service`.
    """
    dashboard = await sharing.resolve_link(token)
    loaded = await dashboards.load(dashboard.id, breakpoint_=breakpoint_, viewer_id=None)
    await audit.record(
        organization_id=dashboard.organization_id,
        action=AuditAction.DASHBOARD_VIEWED,
        entity_type="dashboard",
        entity_id=dashboard.id,
        actor_id=None,
        context={"channel": "link"},
    )
    data = DashboardLoadResponse(
        dashboard=DashboardSummary.model_validate(loaded.dashboard),
        layout=GridResponse.model_validate(loaded.layout.model_dump(mode="json")),
        widgets=[
            ResolvedWidgetResponse.model_validate(widget.as_dict()) for widget in loaded.widgets
        ],
        failed_widgets=loaded.failed_widgets,
        load_ms=loaded.load_ms,
    )
    return SuccessResponse(message="Shared dashboard loaded.", data=data, meta=_meta())


@router.get(
    "/shares",
    response_model=SuccessResponse[list[ShareSummary]],
    summary="List a dashboard's shares",
)
async def list_shares(
    dashboard_id: UUID,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
    roles: CallerRoles,
    active_only: bool = False,
) -> SuccessResponse[list[ShareSummary]]:
    """Return every share of one dashboard, tokens omitted."""
    await _manageable(
        dashboard_id,
        dashboards=dashboards,
        sharing=sharing,
        audit=audit,
        caller=caller,
        roles=roles,
        action=AuditAction.DASHBOARD_SHARED,
    )
    shares = await sharing.list_shares(dashboard_id, active_only=active_only)
    return SuccessResponse(
        message=f"Found {len(shares)} shares.",
        data=[_summary(share) for share in shares],
        meta=_meta(),
    )


@router.delete(
    "/shares/{share_id}",
    response_model=SuccessResponse[ShareSummary],
    summary="Revoke a share",
)
async def revoke_share(
    share_id: UUID,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
    roles: CallerRoles,
) -> SuccessResponse[ShareSummary]:
    """Revoke a share. The row is kept, marked revoked, for the audit trail."""
    share = await sharing.get_share(share_id)
    await _manageable(
        share.dashboard_id,
        dashboards=dashboards,
        sharing=sharing,
        audit=audit,
        caller=caller,
        roles=roles,
        action=AuditAction.SHARE_REVOKED,
    )
    revoked = await sharing.revoke(share_id, revoked_by=caller)
    await audit.record(
        organization_id=revoked.organization_id,
        action=AuditAction.SHARE_REVOKED,
        entity_type="share",
        entity_id=share_id,
        actor_id=caller,
    )
    return SuccessResponse(message="Share revoked.", data=_summary(revoked), meta=_meta())


@router.get(
    "/permissions",
    response_model=SuccessResponse[list[RolePermissionSummary]],
    summary="List role permissions on a dashboard",
)
async def list_permissions(
    dashboard_id: UUID,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
    roles: CallerRoles,
) -> SuccessResponse[list[RolePermissionSummary]]:
    """Return the standing role permissions on one dashboard."""
    await _manageable(
        dashboard_id,
        dashboards=dashboards,
        sharing=sharing,
        audit=audit,
        caller=caller,
        roles=roles,
        action=AuditAction.PERMISSION_CHANGED,
    )
    granted = await sharing.list_role_permissions(dashboard_id)
    return SuccessResponse(
        message=f"Found {len(granted)} role permissions.",
        data=[RolePermissionSummary.model_validate(one) for one in granted],
        meta=_meta(),
    )


@router.post(
    "/permissions",
    response_model=SuccessResponse[RolePermissionSummary],
    status_code=status.HTTP_201_CREATED,
    summary="Grant a role a permission",
)
async def grant_permission(
    body: RolePermissionRequest,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
    roles: CallerRoles,
) -> SuccessResponse[RolePermissionSummary]:
    """Grant or update a role's standing permission."""
    dashboard = await _manageable(
        body.dashboard_id,
        dashboards=dashboards,
        sharing=sharing,
        audit=audit,
        caller=caller,
        roles=roles,
        action=AuditAction.PERMISSION_CHANGED,
    )
    granted = await sharing.grant_role(
        dashboard, role=body.role, permission=body.permission, granted_by=caller
    )
    await audit.record(
        organization_id=dashboard.organization_id,
        action=AuditAction.PERMISSION_CHANGED,
        entity_type="permission",
        entity_id=granted.id,
        actor_id=caller,
        context={"role": body.role, "permission": str(body.permission)},
    )
    return SuccessResponse(
        message=f"Role {body.role!r} granted {str(body.permission)!r} access.",
        data=RolePermissionSummary.model_validate(granted),
        meta=_meta(),
    )


@router.delete(
    "/permissions",
    response_model=SuccessResponse[dict[str, bool]],
    summary="Withdraw a role's permission",
)
async def revoke_permission(
    dashboard_id: UUID,
    role: str,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
    roles: CallerRoles,
) -> SuccessResponse[dict[str, bool]]:
    """Withdraw a role's standing permission."""
    dashboard = await _manageable(
        dashboard_id,
        dashboards=dashboards,
        sharing=sharing,
        audit=audit,
        caller=caller,
        roles=roles,
        action=AuditAction.PERMISSION_CHANGED,
    )
    changed = await sharing.revoke_role(dashboard_id, role)
    if changed:
        await audit.record(
            organization_id=dashboard.organization_id,
            action=AuditAction.PERMISSION_CHANGED,
            entity_type="permission",
            entity_id=dashboard_id,
            actor_id=caller,
            context={"role": role, "revoked": True},
        )
    return SuccessResponse(
        message="Permission withdrawn." if changed else "That role had no permission.",
        data={"changed": changed},
        meta=_meta(),
    )


@router.get(
    "/{dashboard_id}/access",
    response_model=SuccessResponse[AccessResponse],
    summary="What the caller may do with this dashboard",
)
async def my_access(
    dashboard_id: UUID,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    caller: CurrentUserId,
    roles: CallerRoles,
) -> SuccessResponse[AccessResponse]:
    """Report the caller's own rights, so a UI can hide what it cannot do.

    Returns a *verdict*, never an error: asking "may I edit this?" and
    getting a 403 would make the question unanswerable for a viewer.
    """
    dashboard = await dashboards.get_by_id(dashboard_id)
    access = await sharing.resolve_access(dashboard, user_id=caller, roles=roles)
    return SuccessResponse(
        message="Access resolved.",
        data=AccessResponse(
            allowed=access.allowed,
            permission=access.permission,
            can_edit=access.can_edit,
            can_manage=access.can_manage,
            reason=access.reason,
        ),
        meta=_meta(),
    )


__all__ = ["router"]
