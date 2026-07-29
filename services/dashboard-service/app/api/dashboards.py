"""Dashboard, widget, and layout endpoints.

Paths follow docs/048 "REST APIs" exactly. No ``/api/v1`` prefix -- the
gateway owns versioning, the convention every AI-IOS service follows.

**Route order matters here and is deliberate.** docs/048 specifies both
``/dashboards/{id}`` and literal collections like
``/dashboards/widgets``. FastAPI matches in declaration order, so every
literal path is declared *before* the ``{dashboard_id}`` route;
otherwise ``/dashboards/widgets`` would be parsed as a dashboard whose
id is the word "widgets" and return a 422 forever.

**Every read goes through an access check.** ``_readable`` and
``_editable`` resolve the caller's rights through
:class:`~app.services.sharing.SharingService` before anything is
returned, and a refusal is audited as ``DENIED`` -- an attempt to open
a dashboard the caller had no right to is exactly what a security
reviewer is looking for.
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
    DashboardIdQuery,
    DashboardSvc,
    PreferencesSvc,
    SharingSvc,
    StreamingSvc,
)
from app.models.dashboard import Dashboard
from app.models.enums import (
    AuditAction,
    DashboardType,
    LayoutBreakpoint,
    SharePermission,
)
from app.schemas.dashboard import (
    DashboardCreateRequest,
    DashboardLoadResponse,
    DashboardSummary,
    DashboardUpdateRequest,
    FavoriteReorderRequest,
    GridResponse,
    HistoryEntry,
    LayoutRestoreRequest,
    LayoutSaveRequest,
    LayoutSummary,
    ResolvedWidgetResponse,
    SavedFilterRequest,
    SavedFilterSummary,
    WidgetCreateRequest,
    WidgetSettingRequest,
    WidgetSummary,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/dashboards", tags=["Dashboards"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


async def _authorised(
    dashboard_id: UUID,
    *,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    audit: AuditSvc,
    caller: UUID,
    roles: list[str],
    need: SharePermission,
    action: AuditAction,
) -> Dashboard:
    """Load a dashboard the caller may act on, auditing a refusal.

    Raises:
        NotFoundError: If the dashboard does not exist.
        AuthorizationError: If the caller's access is insufficient.
    """
    dashboard = await dashboards.get_by_id(dashboard_id)
    try:
        await sharing.require_access(dashboard, user_id=caller, roles=roles, need=need)
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


# ---- literal collections (must precede "/{dashboard_id}") -----------


@router.get(
    "/widgets",
    response_model=SuccessResponse[list[WidgetSummary]],
    summary="List one dashboard's widgets",
)
async def list_widgets(
    dashboard_id: DashboardIdQuery,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
    roles: CallerRoles,
) -> SuccessResponse[list[WidgetSummary]]:
    """Return every widget on one dashboard, in display order."""
    await _authorised(
        dashboard_id,
        dashboards=dashboards,
        sharing=sharing,
        audit=audit,
        caller=caller,
        roles=roles,
        need=SharePermission.VIEW,
        action=AuditAction.DASHBOARD_VIEWED,
    )
    widgets = await dashboards.list_widgets(dashboard_id)
    return SuccessResponse(
        message=f"Found {len(widgets)} widgets.",
        data=[WidgetSummary.model_validate(widget) for widget in widgets],
        meta=_meta(),
    )


@router.post(
    "/widgets",
    response_model=SuccessResponse[WidgetSummary],
    status_code=status.HTTP_201_CREATED,
    summary="Add a widget to a dashboard",
)
async def add_widget(
    body: WidgetCreateRequest,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
    roles: CallerRoles,
) -> SuccessResponse[WidgetSummary]:
    """Add a widget, validating that it can actually render."""
    dashboard = await _authorised(
        body.dashboard_id,
        dashboards=dashboards,
        sharing=sharing,
        audit=audit,
        caller=caller,
        roles=roles,
        need=SharePermission.EDIT,
        action=AuditAction.WIDGET_ADDED,
    )
    widget = await dashboards.add_widget(
        body.dashboard_id,
        definition=body.definition,
        refresh_mode=body.refresh_mode,
        refresh_seconds=body.refresh_seconds,
        cache_seconds=body.cache_seconds,
        actor_id=caller,
    )
    await audit.record(
        organization_id=dashboard.organization_id,
        action=AuditAction.WIDGET_ADDED,
        entity_type="widget",
        entity_id=widget.id,
        actor_id=caller,
        context={"widget_key": widget.widget_key},
    )
    return SuccessResponse(
        message=f"Widget {widget.widget_key!r} added.",
        data=WidgetSummary.model_validate(widget),
        meta=_meta(),
    )


@router.get(
    "/layouts",
    response_model=SuccessResponse[list[LayoutSummary]],
    summary="List one dashboard's saved layout revisions",
)
async def list_layouts(
    dashboard_id: DashboardIdQuery,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
    roles: CallerRoles,
    breakpoint_: Annotated[LayoutBreakpoint, Query(alias="breakpoint")] = (
        LayoutBreakpoint.DESKTOP
    ),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> SuccessResponse[list[LayoutSummary]]:
    """Return saved revisions for one breakpoint, newest first."""
    await _authorised(
        dashboard_id,
        dashboards=dashboards,
        sharing=sharing,
        audit=audit,
        caller=caller,
        roles=roles,
        need=SharePermission.VIEW,
        action=AuditAction.DASHBOARD_VIEWED,
    )
    layouts = await dashboards.list_layout_revisions(dashboard_id, breakpoint_, limit=limit)
    return SuccessResponse(
        message=f"Found {len(layouts)} layout revisions.",
        data=[LayoutSummary.model_validate(layout) for layout in layouts],
        meta=_meta(),
    )


@router.post(
    "/layouts",
    response_model=SuccessResponse[LayoutSummary],
    status_code=status.HTTP_201_CREATED,
    summary="Save a layout revision",
)
async def save_layout(
    body: LayoutSaveRequest,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    audit: AuditSvc,
    streaming: StreamingSvc,
    caller: CurrentUserId,
    roles: CallerRoles,
) -> SuccessResponse[LayoutSummary]:
    """Save a new revision and tell live watchers it moved."""
    dashboard = await _authorised(
        body.dashboard_id,
        dashboards=dashboards,
        sharing=sharing,
        audit=audit,
        caller=caller,
        roles=roles,
        need=SharePermission.EDIT,
        action=AuditAction.LAYOUT_CHANGED,
    )
    layout = await dashboards.save_layout(
        body.dashboard_id,
        breakpoint_=body.breakpoint_,
        placements=[placement.model_dump() for placement in body.placements],
        columns=body.columns,
        row_height=body.row_height,
        name=body.name,
        actor_id=caller,
    )
    await streaming.notify_layout_changed(body.dashboard_id, revision=layout.revision)
    await audit.record(
        organization_id=dashboard.organization_id,
        action=AuditAction.LAYOUT_CHANGED,
        entity_type="layout",
        entity_id=layout.id,
        actor_id=caller,
        context={"revision": layout.revision, "breakpoint": str(body.breakpoint_)},
    )
    return SuccessResponse(
        message=f"Layout saved as revision {layout.revision}.",
        data=LayoutSummary.model_validate(layout),
        meta=_meta(),
    )


@router.put(
    "/widgets/{widget_id}/settings",
    response_model=SuccessResponse[dict[str, object]],
    summary="Set the caller's own overrides for one widget",
)
async def set_widget_setting(
    widget_id: UUID,
    body: WidgetSettingRequest,
    preferences: PreferencesSvc,
    caller: CurrentUserId,
) -> SuccessResponse[dict[str, object]]:
    """Store per-user widget overrides.

    Needs no dashboard-level edit right: this changes nothing anyone
    else sees, which is the entire point of storing it per user.
    """
    setting = await preferences.set_widget_setting(
        widget_id,
        user_id=caller,
        collapsed=body.collapsed,
        hidden=body.hidden,
        refresh_seconds_override=body.refresh_seconds_override,
        options_override=body.options_override,
    )
    return SuccessResponse(
        message="Widget settings saved.",
        data={
            "widget_id": str(setting.widget_id),
            "collapsed": setting.collapsed,
            "hidden": setting.hidden,
            "refresh_seconds_override": setting.refresh_seconds_override,
        },
        meta=_meta(),
    )


@router.get(
    "/favorites",
    response_model=SuccessResponse[list[DashboardSummary]],
    summary="List the caller's favourite dashboards",
)
async def list_favorites(
    organization_id: UUID, preferences: PreferencesSvc, caller: CurrentUserId
) -> SuccessResponse[list[DashboardSummary]]:
    """Return the dashboards this user pinned, in their own order."""
    found = await preferences.list_favorites(organization_id=organization_id, user_id=caller)
    return SuccessResponse(
        message=f"Found {len(found)} favourites.",
        data=[DashboardSummary.model_validate(one) for one in found],
        meta=_meta(),
    )


@router.put(
    "/favorites",
    response_model=SuccessResponse[list[DashboardSummary]],
    summary="Reorder the caller's favourites",
)
async def reorder_favorites(
    organization_id: UUID,
    body: FavoriteReorderRequest,
    preferences: PreferencesSvc,
    caller: CurrentUserId,
) -> SuccessResponse[list[DashboardSummary]]:
    """Set the display order of this user's favourites."""
    await preferences.reorder_favorites(
        organization_id=organization_id, user_id=caller, dashboard_ids=body.dashboard_ids
    )
    found = await preferences.list_favorites(organization_id=organization_id, user_id=caller)
    return SuccessResponse(
        message="Favourites reordered.",
        data=[DashboardSummary.model_validate(one) for one in found],
        meta=_meta(),
    )


# ---- collection ----------------------------------------------------


@router.get(
    "",
    response_model=SuccessResponse[list[DashboardSummary]],
    summary="List dashboards",
)
async def list_dashboards(
    organization_id: UUID,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    caller: CurrentUserId,
    roles: CallerRoles,
    dashboard_type: DashboardType | None = None,
    enabled_only: bool = False,
) -> SuccessResponse[list[DashboardSummary]]:
    """Return the dashboards this caller may actually see.

    Filtered by access rather than returning everything in the
    organization: a private dashboard belonging to someone else must not
    appear in a listing, even without its contents.
    """
    found = await dashboards.list_for_org(
        organization_id, dashboard_type=dashboard_type, enabled_only=enabled_only
    )
    visible = [
        dashboard
        for dashboard in found
        if (await sharing.resolve_access(dashboard, user_id=caller, roles=roles)).allowed
    ]
    return SuccessResponse(
        message=f"Found {len(visible)} dashboards.",
        data=[DashboardSummary.model_validate(one) for one in visible],
        meta=_meta(),
    )


@router.post(
    "",
    response_model=SuccessResponse[DashboardSummary],
    status_code=status.HTTP_201_CREATED,
    summary="Create a dashboard",
)
async def create_dashboard(
    organization_id: UUID,
    body: DashboardCreateRequest,
    dashboards: DashboardSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[DashboardSummary]:
    """Create a dashboard owned by the calling user."""
    dashboard = await dashboards.create(
        organization_id=organization_id,
        project_id=body.project_id,
        slug=body.slug,
        name=body.name,
        description=body.description,
        dashboard_type=body.dashboard_type,
        visibility=body.visibility,
        theme_id=body.theme_id,
        owner_id=caller,
        default_filters=body.default_filters,
        refresh_seconds=body.refresh_seconds,
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.DASHBOARD_CREATED,
        entity_type="dashboard",
        entity_id=dashboard.id,
        actor_id=caller,
        context={"slug": dashboard.slug},
    )
    return SuccessResponse(
        message=f"Dashboard {dashboard.name!r} created.",
        data=DashboardSummary.model_validate(dashboard),
        meta=_meta(),
    )


# ---- one dashboard -------------------------------------------------


@router.get(
    "/{dashboard_id}",
    response_model=SuccessResponse[DashboardSummary],
    summary="Get one dashboard",
)
async def get_dashboard(
    dashboard_id: UUID,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
    roles: CallerRoles,
) -> SuccessResponse[DashboardSummary]:
    """Return one dashboard's own settings, without loading its widgets."""
    dashboard = await _authorised(
        dashboard_id,
        dashboards=dashboards,
        sharing=sharing,
        audit=audit,
        caller=caller,
        roles=roles,
        need=SharePermission.VIEW,
        action=AuditAction.DASHBOARD_VIEWED,
    )
    return SuccessResponse(
        message="Dashboard retrieved.",
        data=DashboardSummary.model_validate(dashboard),
        meta=_meta(),
    )


@router.put(
    "/{dashboard_id}",
    response_model=SuccessResponse[DashboardSummary],
    summary="Update a dashboard",
)
async def update_dashboard(
    dashboard_id: UUID,
    body: DashboardUpdateRequest,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
    roles: CallerRoles,
) -> SuccessResponse[DashboardSummary]:
    """Update a dashboard's own settings."""
    dashboard = await _authorised(
        dashboard_id,
        dashboards=dashboards,
        sharing=sharing,
        audit=audit,
        caller=caller,
        roles=roles,
        need=SharePermission.EDIT,
        action=AuditAction.DASHBOARD_UPDATED,
    )
    updated = await dashboards.update(
        dashboard_id,
        name=body.name,
        description=body.description,
        visibility=body.visibility,
        theme_id=body.theme_id,
        default_filters=body.default_filters,
        refresh_seconds=body.refresh_seconds,
        enabled=body.enabled,
        actor_id=caller,
    )
    await audit.record(
        organization_id=dashboard.organization_id,
        action=AuditAction.DASHBOARD_UPDATED,
        entity_type="dashboard",
        entity_id=dashboard_id,
        actor_id=caller,
    )
    return SuccessResponse(
        message="Dashboard updated.",
        data=DashboardSummary.model_validate(updated),
        meta=_meta(),
    )


@router.delete(
    "/{dashboard_id}",
    response_model=SuccessResponse[dict[str, str]],
    summary="Delete a dashboard",
)
async def delete_dashboard(
    dashboard_id: UUID,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
    roles: CallerRoles,
) -> SuccessResponse[dict[str, str]]:
    """Soft-delete a dashboard. Requires ``manage`` access."""
    dashboard = await _authorised(
        dashboard_id,
        dashboards=dashboards,
        sharing=sharing,
        audit=audit,
        caller=caller,
        roles=roles,
        need=SharePermission.MANAGE,
        action=AuditAction.DASHBOARD_DELETED,
    )
    await dashboards.delete(dashboard_id, deleted_by=caller)
    await audit.record(
        organization_id=dashboard.organization_id,
        action=AuditAction.DASHBOARD_DELETED,
        entity_type="dashboard",
        entity_id=dashboard_id,
        actor_id=caller,
        context={"slug": dashboard.slug},
    )
    return SuccessResponse(
        message="Dashboard deleted.", data={"dashboard_id": str(dashboard_id)}, meta=_meta()
    )


@router.get(
    "/{dashboard_id}/load",
    response_model=SuccessResponse[DashboardLoadResponse],
    summary="Load a dashboard with every widget resolved",
)
async def load_dashboard(
    dashboard_id: UUID,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
    roles: CallerRoles,
    breakpoint_: Annotated[LayoutBreakpoint, Query(alias="breakpoint")] = (
        LayoutBreakpoint.DESKTOP
    ),
) -> SuccessResponse[DashboardLoadResponse]:
    """Resolve every widget and return the dashboard ready to render.

    A widget that fails comes back as a ``FAILED`` tile carrying its
    reason; the load itself still succeeds. Losing an entire dashboard
    because one source is down is the wrong failure mode for the thing
    an operator watches during an incident.
    """
    dashboard = await _authorised(
        dashboard_id,
        dashboards=dashboards,
        sharing=sharing,
        audit=audit,
        caller=caller,
        roles=roles,
        need=SharePermission.VIEW,
        action=AuditAction.DASHBOARD_VIEWED,
    )
    loaded = await dashboards.load(dashboard_id, breakpoint_=breakpoint_, viewer_id=caller)
    await audit.record(
        organization_id=dashboard.organization_id,
        action=AuditAction.DASHBOARD_VIEWED,
        entity_type="dashboard",
        entity_id=dashboard_id,
        actor_id=caller,
        context={"failed_widgets": loaded.failed_widgets},
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
    return SuccessResponse(message="Dashboard loaded.", data=data, meta=_meta())


@router.get(
    "/{dashboard_id}/layout",
    response_model=SuccessResponse[GridResponse],
    summary="Get the current arrangement",
)
async def get_layout(
    dashboard_id: UUID,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
    roles: CallerRoles,
    breakpoint_: Annotated[LayoutBreakpoint, Query(alias="breakpoint")] = (
        LayoutBreakpoint.DESKTOP
    ),
) -> SuccessResponse[GridResponse]:
    """Return the current layout, reconciled against existing widgets."""
    await _authorised(
        dashboard_id,
        dashboards=dashboards,
        sharing=sharing,
        audit=audit,
        caller=caller,
        roles=roles,
        need=SharePermission.VIEW,
        action=AuditAction.DASHBOARD_VIEWED,
    )
    grid = await dashboards.get_layout(dashboard_id, breakpoint_)
    return SuccessResponse(
        message="Layout retrieved.",
        data=GridResponse.model_validate(grid.model_dump(mode="json")),
        meta=_meta(),
    )


@router.post(
    "/{dashboard_id}/layout/restore",
    response_model=SuccessResponse[LayoutSummary],
    summary="Restore an earlier layout revision",
)
async def restore_layout(
    dashboard_id: UUID,
    body: LayoutRestoreRequest,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    audit: AuditSvc,
    streaming: StreamingSvc,
    caller: CurrentUserId,
    roles: CallerRoles,
) -> SuccessResponse[LayoutSummary]:
    """Make an earlier revision current again ("Undo/Redo")."""
    dashboard = await _authorised(
        dashboard_id,
        dashboards=dashboards,
        sharing=sharing,
        audit=audit,
        caller=caller,
        roles=roles,
        need=SharePermission.EDIT,
        action=AuditAction.LAYOUT_RESTORED,
    )
    layout = await dashboards.restore_layout(
        dashboard_id, breakpoint_=body.breakpoint_, revision=body.revision, actor_id=caller
    )
    await streaming.notify_layout_changed(dashboard_id, revision=layout.revision)
    await audit.record(
        organization_id=dashboard.organization_id,
        action=AuditAction.LAYOUT_RESTORED,
        entity_type="layout",
        entity_id=layout.id,
        actor_id=caller,
        context={"revision": layout.revision},
    )
    return SuccessResponse(
        message=f"Layout restored to revision {layout.revision}.",
        data=LayoutSummary.model_validate(layout),
        meta=_meta(),
    )


@router.delete(
    "/{dashboard_id}/widgets/{widget_key}",
    response_model=SuccessResponse[dict[str, str]],
    summary="Remove a widget",
)
async def remove_widget(
    dashboard_id: UUID,
    widget_key: str,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
    roles: CallerRoles,
) -> SuccessResponse[dict[str, str]]:
    """Remove a widget and reconcile every saved layout."""
    dashboard = await _authorised(
        dashboard_id,
        dashboards=dashboards,
        sharing=sharing,
        audit=audit,
        caller=caller,
        roles=roles,
        need=SharePermission.EDIT,
        action=AuditAction.WIDGET_REMOVED,
    )
    await dashboards.remove_widget(dashboard_id, widget_key, actor_id=caller)
    await audit.record(
        organization_id=dashboard.organization_id,
        action=AuditAction.WIDGET_REMOVED,
        entity_type="widget",
        entity_id=dashboard_id,
        actor_id=caller,
        context={"widget_key": widget_key},
    )
    return SuccessResponse(
        message=f"Widget {widget_key!r} removed.", data={"widget_key": widget_key}, meta=_meta()
    )


@router.get(
    "/{dashboard_id}/history",
    response_model=SuccessResponse[list[HistoryEntry]],
    summary="List a dashboard's activity",
)
async def list_history(
    dashboard_id: UUID,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
    roles: CallerRoles,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> SuccessResponse[list[HistoryEntry]]:
    """Return the user-facing activity trail for one dashboard."""
    await _authorised(
        dashboard_id,
        dashboards=dashboards,
        sharing=sharing,
        audit=audit,
        caller=caller,
        roles=roles,
        need=SharePermission.VIEW,
        action=AuditAction.DASHBOARD_VIEWED,
    )
    entries = await dashboards.list_history(dashboard_id, limit=limit)
    return SuccessResponse(
        message=f"Found {len(entries)} history entries.",
        data=[HistoryEntry.model_validate(entry) for entry in entries],
        meta=_meta(),
    )


@router.post(
    "/{dashboard_id}/favorite",
    response_model=SuccessResponse[dict[str, str]],
    summary="Pin a dashboard",
)
async def add_favorite(
    dashboard_id: UUID, preferences: PreferencesSvc, caller: CurrentUserId
) -> SuccessResponse[dict[str, str]]:
    """Pin a dashboard for the calling user. Idempotent."""
    await preferences.add_favorite(user_id=caller, dashboard_id=dashboard_id)
    return SuccessResponse(
        message="Dashboard pinned.", data={"dashboard_id": str(dashboard_id)}, meta=_meta()
    )


@router.delete(
    "/{dashboard_id}/favorite",
    response_model=SuccessResponse[dict[str, bool]],
    summary="Unpin a dashboard",
)
async def remove_favorite(
    dashboard_id: UUID, preferences: PreferencesSvc, caller: CurrentUserId
) -> SuccessResponse[dict[str, bool]]:
    """Unpin a dashboard for the calling user."""
    removed = await preferences.remove_favorite(user_id=caller, dashboard_id=dashboard_id)
    return SuccessResponse(
        message="Dashboard unpinned." if removed else "It was not pinned.",
        data={"removed": removed},
        meta=_meta(),
    )


@router.get(
    "/{dashboard_id}/filters",
    response_model=SuccessResponse[list[SavedFilterSummary]],
    summary="List saved filters",
)
async def list_filters(
    dashboard_id: UUID,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    audit: AuditSvc,
    preferences: PreferencesSvc,
    caller: CurrentUserId,
    roles: CallerRoles,
) -> SuccessResponse[list[SavedFilterSummary]]:
    """Return the caller's own saved filters plus the shared presets."""
    await _authorised(
        dashboard_id,
        dashboards=dashboards,
        sharing=sharing,
        audit=audit,
        caller=caller,
        roles=roles,
        need=SharePermission.VIEW,
        action=AuditAction.DASHBOARD_VIEWED,
    )
    saved = await preferences.list_filters(dashboard_id, user_id=caller)
    return SuccessResponse(
        message=f"Found {len(saved)} saved filters.",
        data=[SavedFilterSummary.model_validate(one) for one in saved],
        meta=_meta(),
    )


@router.post(
    "/{dashboard_id}/filters",
    response_model=SuccessResponse[SavedFilterSummary],
    status_code=status.HTTP_201_CREATED,
    summary="Save a filter set",
)
async def save_filter(
    dashboard_id: UUID,
    body: SavedFilterRequest,
    dashboards: DashboardSvc,
    sharing: SharingSvc,
    audit: AuditSvc,
    preferences: PreferencesSvc,
    caller: CurrentUserId,
    roles: CallerRoles,
) -> SuccessResponse[SavedFilterSummary]:
    """Save a named filter set.

    Saving a *shared* preset changes what everyone sees, so it needs
    edit access; saving a personal one needs only view.
    """
    await _authorised(
        dashboard_id,
        dashboards=dashboards,
        sharing=sharing,
        audit=audit,
        caller=caller,
        roles=roles,
        need=SharePermission.EDIT if body.shared else SharePermission.VIEW,
        action=AuditAction.DASHBOARD_UPDATED,
    )
    saved = await preferences.save_filter(
        dashboard_id,
        name=body.name,
        clauses=body.clauses,
        user_id=None if body.shared else caller,
        is_default=body.is_default,
    )
    return SuccessResponse(
        message=f"Filter {saved.name!r} saved.",
        data=SavedFilterSummary.model_validate(saved),
        meta=_meta(),
    )


__all__ = ["router"]
