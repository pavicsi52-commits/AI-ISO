"""Dashboard CRUD, widgets, layouts, and loading.

This is the service's own central pipeline. Loading one dashboard:

1. Resolve the dashboard and check the caller may see it.
2. Read its widgets and the current layout for the requested
   breakpoint, reconciling the layout against the widgets that
   actually exist.
3. Resolve every widget's data **concurrently** (bounded).
4. Record the view for analytics.

**Every database write is sequential.** Only widget data-source fetches
overlap, and those touch no session -- an ``AsyncSession`` is not safe
for concurrent use even for reads.

**Enum columns come back as ``str``.** Every comparison here goes
through an explicit normaliser rather than ``is``; that mistake has
shipped as a live bug four times across this platform.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError
from shared_core.logging.logger import get_logger

from app.events.dashboard_events import (
    SOURCE_SERVICE,
    DashboardCreatedEvent,
    DashboardDeletedEvent,
    DashboardUpdatedEvent,
    LayoutChangedEvent,
    WidgetAddedEvent,
    WidgetRemovedEvent,
)
from app.filters.engine import FilterClause, parse_clauses
from app.layouts.grid import GridLayout, parse_placements, synchronise
from app.models.dashboard import Dashboard
from app.models.dashboard_history import DashboardHistory
from app.models.dashboard_layout import DashboardLayout
from app.models.dashboard_view import DashboardView
from app.models.dashboard_widget import DashboardWidget
from app.models.enums import (
    DashboardType,
    DashboardVisibility,
    LayoutBreakpoint,
    RefreshMode,
)
from app.repositories.dashboard import DashboardRepository
from app.repositories.dashboard_history import DashboardHistoryRepository
from app.repositories.dashboard_layout import DashboardLayoutRepository
from app.repositories.dashboard_view import DashboardViewRepository
from app.repositories.dashboard_widget import DashboardWidgetRepository
from app.types import EventPublisher
from app.widgets.resolver import ResolvedWidget, WidgetResolver
from app.widgets.schema import parse_widget

logger = get_logger("app.services.dashboard")


def visibility_of(dashboard: Dashboard) -> DashboardVisibility:
    """A dashboard's visibility as a genuine enum member.

    ``visibility`` is annotated ``Mapped[DashboardVisibility]`` but
    stored in a plain ``String``, so a row loaded from Postgres yields
    a raw ``str``. Comparing that with ``is`` is ``False`` for every
    stored row -- normalising once here is what keeps the access checks
    meaning what they read as.
    """
    value = dashboard.visibility
    return value if isinstance(value, DashboardVisibility) else DashboardVisibility(value)


def breakpoint_of(layout: DashboardLayout) -> LayoutBreakpoint:
    """A layout's breakpoint as a genuine enum member."""
    value = layout.breakpoint
    return value if isinstance(value, LayoutBreakpoint) else LayoutBreakpoint(value)


@dataclass(slots=True)
class LoadedDashboard:
    """Everything one dashboard load produced."""

    dashboard: Dashboard
    layout: GridLayout
    widgets: list[ResolvedWidget] = field(default_factory=list)
    load_ms: float | None = None

    @property
    def failed_widgets(self) -> list[str]:
        """Widget keys that could not be resolved."""
        return [widget.widget_key for widget in self.widgets if widget.failed]


class DashboardService:
    """Creates, reads, updates, and loads dashboards."""

    def __init__(
        self,
        dashboards: DashboardRepository,
        widgets: DashboardWidgetRepository,
        layouts: DashboardLayoutRepository,
        history: DashboardHistoryRepository,
        views: DashboardViewRepository,
        resolver: WidgetResolver,
        *,
        publish_event: EventPublisher,
        max_widgets: int = 60,
    ) -> None:
        self._dashboards = dashboards
        self._widgets = widgets
        self._layouts = layouts
        self._history = history
        self._views = views
        self._resolver = resolver
        self._publish_event = publish_event
        self._max_widgets = max_widgets

    async def get_by_id(self, dashboard_id: UUID) -> Dashboard:
        """Return one dashboard.

        Raises:
            NotFoundError: If no such dashboard exists.
        """
        return await self._dashboards.require_by_id(dashboard_id)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        dashboard_type: DashboardType | None = None,
        enabled_only: bool = False,
    ) -> list[Dashboard]:
        """Dashboards for an organization."""
        return await self._dashboards.list_for_org(
            organization_id, dashboard_type=dashboard_type, enabled_only=enabled_only
        )

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        slug: str,
        name: str,
        description: str | None,
        dashboard_type: DashboardType,
        visibility: DashboardVisibility = DashboardVisibility.PRIVATE,
        theme_id: UUID | None = None,
        owner_id: UUID | None = None,
        default_filters: list[dict[str, Any]] | None = None,
        refresh_seconds: int = 0,
    ) -> Dashboard:
        """Create a dashboard.

        Filters are parsed on write, so a malformed clause is rejected
        here rather than by every widget at load time.

        Raises:
            ConflictError: If the slug is already used.
            ValidationError: If a default filter is malformed.
        """
        parse_clauses(default_filters or [])
        if await self._dashboards.get_by_slug(organization_id, slug) is not None:
            raise ConflictError(f"A dashboard with slug {slug!r} already exists.")

        dashboard = await self._dashboards.create(
            Dashboard(
                organization_id=organization_id,
                project_id=project_id,
                slug=slug,
                name=name,
                description=description,
                dashboard_type=dashboard_type,
                visibility=visibility,
                theme_id=theme_id,
                owner_id=owner_id,
                default_filters=default_filters or [],
                refresh_seconds=refresh_seconds,
            )
        )
        await self._record_history(
            dashboard, event="created", summary=f"Dashboard {name!r} created.", actor_id=owner_id
        )
        await self._publish_event(
            DashboardCreatedEvent(
                source_service=SOURCE_SERVICE,
                payload={"dashboard_id": str(dashboard.id), "name": name, "slug": slug},
            )
        )
        return dashboard

    async def update(
        self,
        dashboard_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        visibility: DashboardVisibility | None = None,
        theme_id: UUID | None = None,
        default_filters: list[dict[str, Any]] | None = None,
        refresh_seconds: int | None = None,
        enabled: bool | None = None,
        actor_id: UUID | None = None,
    ) -> Dashboard:
        """Update a dashboard in place.

        Raises:
            NotFoundError: If no such dashboard exists.
            ValidationError: If a default filter is malformed.
        """
        dashboard = await self._dashboards.require_by_id(dashboard_id)
        if default_filters is not None:
            parse_clauses(default_filters)
            dashboard.default_filters = default_filters
        if name is not None:
            dashboard.name = name
        if description is not None:
            dashboard.description = description
        if visibility is not None:
            dashboard.visibility = visibility
        if theme_id is not None:
            dashboard.theme_id = theme_id
        if refresh_seconds is not None:
            dashboard.refresh_seconds = refresh_seconds
        if enabled is not None:
            dashboard.enabled = enabled

        updated = await self._dashboards.update(dashboard)
        await self._record_history(
            updated, event="updated", summary="Dashboard settings changed.", actor_id=actor_id
        )
        await self._publish_event(
            DashboardUpdatedEvent(
                source_service=SOURCE_SERVICE, payload={"dashboard_id": str(updated.id)}
            )
        )
        return updated

    async def delete(self, dashboard_id: UUID, *, deleted_by: UUID | None = None) -> None:
        """Soft-delete a dashboard.

        Soft rather than hard: views, shares, and audit entries
        reference it, and an audit trail that dangles is worse than one
        pointing at a retired row.

        Raises:
            NotFoundError: If no such dashboard exists.
        """
        dashboard = await self._dashboards.require_by_id(dashboard_id)
        await self._dashboards.delete(dashboard_id, deleted_by=deleted_by)
        await self._publish_event(
            DashboardDeletedEvent(
                source_service=SOURCE_SERVICE,
                payload={"dashboard_id": str(dashboard_id), "name": dashboard.name},
            )
        )

    # ---- widgets ---------------------------------------------------

    async def list_widgets(self, dashboard_id: UUID) -> list[DashboardWidget]:
        """Every widget on one dashboard, in display order."""
        return await self._widgets.list_for_dashboard(dashboard_id)

    async def add_widget(
        self,
        dashboard_id: UUID,
        *,
        definition: dict[str, Any],
        refresh_mode: RefreshMode = RefreshMode.POLLING,
        refresh_seconds: int = 60,
        cache_seconds: int = 30,
        actor_id: UUID | None = None,
    ) -> DashboardWidget:
        """Add a widget, validating it can actually render.

        The widget is also placed on every existing layout, so it is
        visible immediately rather than existing but unplaced until
        someone drags it in.

        Raises:
            NotFoundError: If the dashboard does not exist.
            ConflictError: If the key is taken or the ceiling is reached.
            ValidationError: If the definition cannot render.
        """
        dashboard = await self._dashboards.require_by_id(dashboard_id)
        try:
            parsed = parse_widget(definition)
        except Exception as exc:
            raise ValidationError(f"Invalid widget definition: {exc}") from exc

        if await self._widgets.get_by_key(dashboard_id, parsed.widget_key) is not None:
            raise ConflictError(f"Widget key {parsed.widget_key!r} is already used here.")
        if await self._widgets.count_for_dashboard(dashboard_id) >= self._max_widgets:
            raise ConflictError(
                f"This dashboard already has the maximum of {self._max_widgets} widgets."
            )

        widget = await self._widgets.create(
            DashboardWidget(
                organization_id=dashboard.organization_id,
                project_id=dashboard.project_id,
                dashboard_id=dashboard_id,
                widget_key=parsed.widget_key,
                title=parsed.title,
                widget_type=parsed.widget_type,
                data_source=parsed.query.source,
                query=parsed.query.model_dump(mode="json"),
                options=parsed.options.model_dump(mode="json"),
                refresh_mode=refresh_mode,
                refresh_seconds=refresh_seconds,
                cache_seconds=cache_seconds,
            )
        )
        await self._reconcile_layouts(dashboard_id)
        await self._record_history(
            dashboard,
            event="widget_added",
            summary=f"Widget {parsed.title!r} added.",
            actor_id=actor_id,
            details={"widget_key": parsed.widget_key},
        )
        await self._publish_event(
            WidgetAddedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "dashboard_id": str(dashboard_id),
                    "widget_key": parsed.widget_key,
                    "widget_type": str(parsed.widget_type),
                },
            )
        )
        return widget

    async def remove_widget(
        self, dashboard_id: UUID, widget_key: str, *, actor_id: UUID | None = None
    ) -> None:
        """Remove a widget and its placements.

        Raises:
            NotFoundError: If the dashboard or widget does not exist.
        """
        dashboard = await self._dashboards.require_by_id(dashboard_id)
        widget = await self._widgets.get_by_key(dashboard_id, widget_key)
        if widget is None:
            raise NotFoundError(f"Widget {widget_key!r} is not on this dashboard.")

        await self._widgets.purge(widget.id)
        await self._reconcile_layouts(dashboard_id)
        await self._record_history(
            dashboard,
            event="widget_removed",
            summary=f"Widget {widget.title!r} removed.",
            actor_id=actor_id,
            details={"widget_key": widget_key},
        )
        await self._publish_event(
            WidgetRemovedEvent(
                source_service=SOURCE_SERVICE,
                payload={"dashboard_id": str(dashboard_id), "widget_key": widget_key},
            )
        )

    # ---- layouts ---------------------------------------------------

    async def get_layout(
        self, dashboard_id: UUID, breakpoint_: LayoutBreakpoint = LayoutBreakpoint.DESKTOP
    ) -> GridLayout:
        """The current layout, reconciled against existing widgets.

        A layout is always returned, even when none was ever saved: a
        dashboard with widgets and no layout should render in a sane
        default arrangement rather than appearing empty.
        """
        widgets = await self._widgets.list_for_dashboard(dashboard_id)
        keys = {widget.widget_key for widget in widgets}
        stored = await self._layouts.get_current(dashboard_id, breakpoint_)
        if stored is None:
            base = GridLayout()
            return synchronise(base, keys)
        grid = parse_placements(
            stored.placements, columns=stored.columns, row_height=stored.row_height
        )
        return synchronise(grid, keys)

    async def save_layout(
        self,
        dashboard_id: UUID,
        *,
        breakpoint_: LayoutBreakpoint,
        placements: list[dict[str, Any]],
        columns: int = 12,
        row_height: int = 60,
        name: str | None = None,
        actor_id: UUID | None = None,
    ) -> DashboardLayout:
        """Save a new layout revision.

        **Every save is a new row.** Undo/redo and "Saved Layouts" are
        real only if earlier arrangements still exist exactly as they
        were, so nothing is ever edited in place.

        Raises:
            NotFoundError: If the dashboard does not exist.
            ValidationError: If the arrangement overlaps or overflows.
        """
        dashboard = await self._dashboards.require_by_id(dashboard_id)
        grid = parse_placements(placements, columns=columns, row_height=row_height)

        widgets = await self._widgets.list_for_dashboard(dashboard_id)
        known = {widget.widget_key for widget in widgets}
        unknown = sorted(grid.widget_keys() - known)
        if unknown:
            raise ValidationError(
                f"The layout places widgets this dashboard does not have: {', '.join(unknown)}."
            )

        current = await self._layouts.get_current(dashboard_id, breakpoint_)
        if current is not None:
            current.is_current = False
            await self._layouts.update(current)

        revision = await self._layouts.next_revision(dashboard_id, breakpoint_)
        saved = await self._layouts.create(
            DashboardLayout(
                organization_id=dashboard.organization_id,
                project_id=dashboard.project_id,
                dashboard_id=dashboard_id,
                breakpoint=breakpoint_,
                revision=revision,
                name=name,
                columns=grid.columns,
                row_height=grid.row_height,
                placements=[placement.model_dump() for placement in grid.placements],
                is_current=True,
                created_by_user=actor_id,
            )
        )
        dashboard.layout_revision = revision
        await self._dashboards.update(dashboard)

        await self._record_history(
            dashboard,
            event="layout_changed",
            summary=f"Layout saved as revision {revision}.",
            actor_id=actor_id,
            layout_revision=revision,
            details={"breakpoint": str(breakpoint_)},
        )
        await self._publish_event(
            LayoutChangedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "dashboard_id": str(dashboard_id),
                    "breakpoint": str(breakpoint_),
                    "revision": revision,
                },
            )
        )
        return saved

    async def restore_layout(
        self,
        dashboard_id: UUID,
        *,
        breakpoint_: LayoutBreakpoint,
        revision: int,
        actor_id: UUID | None = None,
    ) -> DashboardLayout:
        """Restore an earlier revision by making it current again.

        Restoring points ``is_current`` at the earlier row rather than
        copying it forward, so the undo stack stays a straight history
        instead of accumulating duplicates of the same arrangement.

        Raises:
            NotFoundError: If the dashboard or revision does not exist.
        """
        dashboard = await self._dashboards.require_by_id(dashboard_id)
        target = await self._layouts.get_revision(dashboard_id, breakpoint_, revision)
        if target is None:
            raise NotFoundError(f"Layout revision {revision} does not exist for this breakpoint.")

        current = await self._layouts.get_current(dashboard_id, breakpoint_)
        if current is not None and current.id != target.id:
            current.is_current = False
            await self._layouts.update(current)

        target.is_current = True
        restored = await self._layouts.update(target)
        dashboard.layout_revision = revision
        await self._dashboards.update(dashboard)

        await self._record_history(
            dashboard,
            event="layout_restored",
            summary=f"Layout restored to revision {revision}.",
            actor_id=actor_id,
            layout_revision=revision,
        )
        await self._publish_event(
            LayoutChangedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "dashboard_id": str(dashboard_id),
                    "breakpoint": str(breakpoint_),
                    "revision": revision,
                    "restored": True,
                },
            )
        )
        return restored

    async def list_layout_revisions(
        self, dashboard_id: UUID, breakpoint_: LayoutBreakpoint, *, limit: int = 50
    ) -> list[DashboardLayout]:
        """Saved revisions for one breakpoint, newest first."""
        return await self._layouts.list_revisions(dashboard_id, breakpoint_, limit=limit)

    async def _reconcile_layouts(self, dashboard_id: UUID) -> None:
        """Keep saved layouts consistent with the widgets that exist.

        Runs after a widget is added or removed so a deleted widget
        leaves no hole and a new one is immediately visible.
        """
        widgets = await self._widgets.list_for_dashboard(dashboard_id)
        keys = {widget.widget_key for widget in widgets}
        for layout in await self._layouts.list_for_dashboard(dashboard_id):
            grid = parse_placements(
                layout.placements, columns=layout.columns, row_height=layout.row_height
            )
            reconciled = synchronise(grid, keys)
            layout.placements = [placement.model_dump() for placement in reconciled.placements]
            await self._layouts.update(layout)

    # ---- loading ---------------------------------------------------

    async def load(
        self,
        dashboard_id: UUID,
        *,
        breakpoint_: LayoutBreakpoint = LayoutBreakpoint.DESKTOP,
        extra_filters: list[dict[str, Any]] | None = None,
        parameters: dict[str, Any] | None = None,
        viewer_id: UUID | None = None,
        record_view: bool = True,
    ) -> LoadedDashboard:
        """Load a dashboard: layout plus every widget resolved.

        Widget failures never fail the load -- each failed tile carries
        its own reason. That is deliberate: a dashboard is what an
        operator stares at during an incident, and losing all of it
        because one source is down is the wrong failure mode.

        Raises:
            NotFoundError: If the dashboard does not exist.
            ValidationError: If a supplied filter is malformed.
        """
        started = time.monotonic()
        dashboard = await self._dashboards.require_by_id(dashboard_id)
        widgets = await self._widgets.list_for_dashboard(dashboard_id, enabled_only=True)
        layout = await self.get_layout(dashboard_id, breakpoint_)

        clauses: list[FilterClause] = parse_clauses(
            [*dashboard.default_filters, *(extra_filters or [])]
        )
        resolved = await self._resolver.resolve_many(
            widgets,
            organization_id=dashboard.organization_id,
            dashboard_filters=clauses,
            parameters=parameters,
        )
        load_ms = (time.monotonic() - started) * 1000

        if record_view:
            await self._views.create(
                DashboardView(
                    organization_id=dashboard.organization_id,
                    project_id=dashboard.project_id,
                    dashboard_id=dashboard_id,
                    user_id=viewer_id,
                    load_ms=load_ms,
                    widget_count=len(resolved),
                    failed_widget_count=sum(1 for widget in resolved if widget.failed),
                    viewed_at=datetime.now(UTC),
                )
            )

        failed = [widget.widget_key for widget in resolved if widget.failed]
        if failed:
            logger.warning(
                "Dashboard loaded with failed widgets.",
                extra={"extra_fields": {"dashboard_id": str(dashboard_id), "widgets": failed}},
            )
        return LoadedDashboard(
            dashboard=dashboard, layout=layout, widgets=resolved, load_ms=load_ms
        )

    async def list_history(self, dashboard_id: UUID, *, limit: int = 100) -> list[DashboardHistory]:
        """Activity on one dashboard."""
        return await self._history.list_for_dashboard(dashboard_id, limit=limit)

    async def _record_history(
        self,
        dashboard: Dashboard,
        *,
        event: str,
        summary: str,
        actor_id: UUID | None,
        layout_revision: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> DashboardHistory:
        """Append one user-visible history entry."""
        return await self._history.create(
            DashboardHistory(
                organization_id=dashboard.organization_id,
                project_id=dashboard.project_id,
                dashboard_id=dashboard.id,
                event=event,
                summary=summary,
                details=details or {},
                layout_revision=layout_revision,
                actor_id=actor_id,
                occurred_at=datetime.now(UTC),
            )
        )


__all__ = [
    "DashboardService",
    "LoadedDashboard",
    "breakpoint_of",
    "visibility_of",
]
