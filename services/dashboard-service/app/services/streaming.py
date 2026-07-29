"""Live dashboard updates ("REAL-TIME UPDATES").

Ties :class:`~app.realtime.hub.DashboardHub` to the data pipeline: the
hub knows *who* is watching, this knows *what to tell them*.

**Fan-out carries notifications, never resolved data.** Every widget in
this service is resolved with the *viewing user's own bearer token*, so
a dashboard can never show data that user could not have fetched
themselves. A broadcast frame goes to every watcher of a dashboard at
once, and those watchers are different people with different rights --
so pushing one user's resolved rows down that channel would hand
whatever they could see to everyone else watching. Frames therefore say
*that* something changed and the client re-fetches over HTTP under its
own credentials. It costs one extra round trip and it is the only
shape that keeps the RBAC guarantee intact.

The single exception is :meth:`StreamingService.snapshot`, which is
resolved with the connecting caller's own token and returned down that
caller's own connection -- it is never fanned out.

**Nothing is sent to a dashboard nobody is watching.** Every push asks
the hub first and returns immediately if there are no subscribers.
Without that check, a hundred idle dashboards would each wake a timer
for an audience of nobody.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from app.models.enums import LayoutBreakpoint, StreamEventKind
from app.realtime.hub import DashboardHub, StreamEvent, Subscriber
from app.services.dashboard import DashboardService

RELOAD_ACTION = "reload"
"""What a client should do on an update frame: re-fetch under its own token."""


class StreamingService:
    """Serves snapshots and notifies watchers that a dashboard changed."""

    def __init__(self, hub: DashboardHub, dashboards: DashboardService) -> None:
        self._hub = hub
        self._dashboards = dashboards

    def subscribe(self, dashboard_id: UUID, *, user_id: UUID | None = None) -> Subscriber:
        """Register a watcher.

        Raises:
            RuntimeError: If the deployment-wide subscriber ceiling is
                reached.
        """
        return self._hub.subscribe(dashboard_id, user_id=user_id)

    def unsubscribe(self, subscriber: Subscriber) -> None:
        """Remove a watcher; safe to call twice."""
        self._hub.unsubscribe(subscriber)

    def stream(
        self, subscriber: Subscriber, *, heartbeat_seconds: int = 20
    ) -> AsyncIterator[StreamEvent]:
        """Yield frames for one watcher until it disconnects.

        Both transports -- SSE and WebSocket -- consume this, so
        back-pressure, heartbeats, and slow-subscriber eviction behave
        identically on each instead of being implemented twice.
        """
        return self._hub.stream(subscriber, heartbeat_seconds=heartbeat_seconds)

    def presence(self, dashboard_id: UUID) -> list[dict[str, Any]]:
        """Who is currently watching one dashboard, on this replica."""
        return self._hub.presence(dashboard_id)

    def watcher_count(self, dashboard_id: UUID) -> int:
        """How many clients are watching one dashboard, on this replica."""
        return self._hub.count_for(dashboard_id)

    def watched_dashboards(self) -> list[UUID]:
        """Every dashboard with at least one watcher on this replica."""
        return self._hub.watched_dashboards()

    async def snapshot(
        self,
        dashboard_id: UUID,
        *,
        breakpoint_: LayoutBreakpoint = LayoutBreakpoint.DESKTOP,
        viewer_id: UUID | None = None,
    ) -> StreamEvent:
        """Build the first frame a newly connected client receives.

        Resolved with the connecting caller's own token and returned
        down that caller's own connection only -- the one place this
        service puts resolved data on a stream, and the reason it is
        safe.

        The view is **not** recorded: a snapshot is the same load the
        client just performed over HTTP, and counting it again would
        double every view figure for anyone using live updates.
        """
        loaded = await self._dashboards.load(
            dashboard_id,
            breakpoint_=breakpoint_,
            viewer_id=viewer_id,
            record_view=False,
        )
        return StreamEvent(
            kind=StreamEventKind.SNAPSHOT,
            dashboard_id=dashboard_id,
            payload={
                "dashboard": {
                    "id": str(loaded.dashboard.id),
                    "name": loaded.dashboard.name,
                    "slug": loaded.dashboard.slug,
                    "refresh_seconds": loaded.dashboard.refresh_seconds,
                },
                "layout": loaded.layout.model_dump(mode="json"),
                "widgets": [widget.as_dict() for widget in loaded.widgets],
                "load_ms": loaded.load_ms,
            },
        )

    async def notify_stale(
        self, dashboard_id: UUID, *, reason: str, force: bool = False, **details: Any
    ) -> int:
        """Tell watchers their view is out of date; returns how many heard.

        Carries no data, by design -- see this module's docstring. Zero
        is the normal, cheap outcome for a dashboard nobody is watching;
        *force* sends anyway, which only matters for tests and for an
        operator's explicit "refresh now".
        """
        if not force and self._hub.count_for(dashboard_id) == 0:
            return 0
        return await self._hub.publish_update(
            dashboard_id, {"action": RELOAD_ACTION, "reason": reason, **details}
        )

    async def notify_data_refresh(self, dashboard_id: UUID) -> int:
        """Tell watchers a scheduled refresh is due."""
        return await self.notify_stale(dashboard_id, reason="refresh_due")

    async def notify_layout_changed(self, dashboard_id: UUID, *, revision: int) -> int:
        """Tell watchers the layout moved under them ("Collaborative Editing")."""
        return await self.notify_stale(
            dashboard_id, reason="layout_changed", layout_revision=revision
        )

    async def notify_widgets_changed(self, dashboard_id: UUID, *, widget_key: str) -> int:
        """Tell watchers a widget was added or removed."""
        return await self.notify_stale(
            dashboard_id, reason="widgets_changed", widget_key=widget_key
        )

    async def notify_error(self, dashboard_id: UUID, *, error: str) -> int:
        """Tell watchers something went wrong producing their view."""
        return await self._hub.publish(
            StreamEvent(
                kind=StreamEventKind.ERROR,
                dashboard_id=dashboard_id,
                payload={"error": error},
            )
        )

    async def announce_presence(self, dashboard_id: UUID) -> int:
        """Tell everyone watching who else is here."""
        return await self._hub.publish_presence(dashboard_id)


__all__ = ["RELOAD_ACTION", "StreamingService"]
