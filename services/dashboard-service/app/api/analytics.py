"""Analytics, audit, topology, and real-time streaming endpoints.

``GET /dashboards/statistics`` is the path docs/048 names. The audit,
topology, and streaming surfaces sit alongside it under literal
segments, in a router included before :mod:`app.api.dashboards` so none
of them can be parsed as a dashboard id.

**Two streaming transports over one hub.** ``/stream`` is Server-Sent
Events and ``/ws`` is a WebSocket; both read the same
:class:`~app.realtime.hub.Subscriber` queue, so back-pressure,
heartbeats, and slow-subscriber eviction behave identically on each
rather than being implemented twice and drifting apart.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from shared_core.exceptions.dependency import DependencyError
from shared_core.logging.context import get_log_context
from shared_core.logging.logger import get_logger
from shared_core.security.jwt import decode_token

from app.api.deps import (
    AuditSvc,
    CurrentUserId,
    StatisticsSvc,
    StreamingSvc,
    TopologyDep,
)
from app.models.enums import AuditAction, LayoutBreakpoint
from app.schemas.catalog import (
    AuditEntry,
    PresenceResponse,
    StatisticsResponse,
    TopologyRequest,
    TopologyResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

logger = get_logger("app.api.analytics")

router = APIRouter(prefix="/dashboards", tags=["Analytics & Real-time"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get(
    "/statistics",
    response_model=SuccessResponse[StatisticsResponse],
    summary="Dashboard usage analytics",
)
async def get_statistics(
    organization_id: UUID,
    statistics: StatisticsSvc,
    recompute: bool = False,
    window_days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> SuccessResponse[StatisticsResponse]:
    """Return the organization's dashboard analytics rollup.

    With ``recompute=true`` the rollup is derived fresh from the view,
    widget, and share rows. Every figure is *derived*, never
    incremented: a counter bumped per view drifts the moment one write
    is lost, with no way to tell that it has.
    """
    record = (
        await statistics.refresh(organization_id, window_days=window_days)
        if recompute
        else await statistics.get(organization_id)
    )
    if record is None:
        record = await statistics.refresh(organization_id, window_days=window_days)
    return SuccessResponse(
        message="Statistics retrieved.",
        data=StatisticsResponse.model_validate(record),
        meta=_meta(),
    )


@router.get(
    "/{dashboard_id}/statistics",
    response_model=SuccessResponse[dict[str, object]],
    summary="One dashboard's usage",
)
async def get_dashboard_statistics(
    dashboard_id: UUID,
    statistics: StatisticsSvc,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
) -> SuccessResponse[dict[str, object]]:
    """Return view counts and load-time percentiles for one dashboard.

    Median and p95 rather than a mean: a mean is dominated by a handful
    of pathological loads and hides the experience of everyone else.
    """
    data = await statistics.dashboard_usage(dashboard_id, limit=limit)
    return SuccessResponse(message="Dashboard usage computed.", data=data, meta=_meta())


@router.get(
    "/audit",
    response_model=SuccessResponse[list[AuditEntry]],
    summary="Dashboard audit trail",
)
async def list_audit(
    organization_id: UUID,
    audit: AuditSvc,
    action: AuditAction | None = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
) -> SuccessResponse[list[AuditEntry]]:
    """Return audited dashboard actions, most recent first.

    Includes ``DENIED`` outcomes: an attempt to open a dashboard the
    caller had no right to is precisely what an auditor is looking for.
    """
    entries = await audit.list_for_org(organization_id, action=action, limit=limit)
    return SuccessResponse(
        message=f"Found {len(entries)} audit entries.",
        data=[AuditEntry.model_validate(entry) for entry in entries],
        meta=_meta(),
    )


@router.get(
    "/audit/summary",
    response_model=SuccessResponse[dict[str, object]],
    summary="Audit counts by action and outcome",
)
async def audit_summary(
    organization_id: UUID,
    audit: AuditSvc,
    limit: Annotated[int, Query(ge=1, le=5_000)] = 1_000,
) -> SuccessResponse[dict[str, object]]:
    """Return audit counts grouped by action and by outcome."""
    return SuccessResponse(
        message="Audit summarised.",
        data=await audit.summarise(organization_id, limit=limit),
        meta=_meta(),
    )


@router.post(
    "/topology",
    response_model=SuccessResponse[TopologyResponse],
    summary="Run a topology traversal",
)
async def query_topology(
    organization_id: UUID,
    body: TopologyRequest,
    topology: TopologyDep,
    caller: CurrentUserId,
) -> SuccessResponse[TopologyResponse]:
    """Traverse the Prompt 036 graph for a topology view.

    Bounded by depth *and* node count: an unbounded blast-radius query
    on a large estate is an outage, not a visualisation. A graph that
    hit the ceiling comes back flagged ``truncated`` so a viewer knows
    they are looking at a partial picture.

    Raises:
        DependencyError: If topology is unconfigured or Neo4j is down.
    """
    del caller  # authentication is the requirement; the graph is org-scoped
    if not topology.enabled:
        raise DependencyError("Topology visualisation is not configured on this deployment.")
    graph = await topology.query(
        organization_id=str(organization_id),
        root_id=body.root_id,
        kind=body.kind,
        depth=body.depth,
    )
    return SuccessResponse(
        message=(
            "Topology rendered."
            if not graph.truncated
            else "Topology rendered, truncated at the node ceiling."
        ),
        data=TopologyResponse.model_validate(graph.as_dict()),
        meta=_meta(),
    )


@router.get(
    "/{dashboard_id}/presence",
    response_model=SuccessResponse[PresenceResponse],
    summary="Who is watching this dashboard",
)
async def presence(
    dashboard_id: UUID, streaming: StreamingSvc
) -> SuccessResponse[PresenceResponse]:
    """Return the live watchers on *this replica*.

    Replica-scoped because each process knows only its own connections;
    the response says so rather than letting a client read a low number
    as "nobody is here".
    """
    return SuccessResponse(
        message="Presence retrieved.",
        data=PresenceResponse(dashboard_id=dashboard_id, watchers=streaming.presence(dashboard_id)),
        meta=_meta(),
    )


@router.get("/{dashboard_id}/stream", summary="Live updates over Server-Sent Events")
async def stream(
    request: Request,
    dashboard_id: UUID,
    streaming: StreamingSvc,
    caller: CurrentUserId,
    breakpoint_: Annotated[LayoutBreakpoint, Query(alias="breakpoint")] = (
        LayoutBreakpoint.DESKTOP
    ),
) -> StreamingResponse:
    """Stream dashboard frames as SSE.

    A snapshot is sent first so a client joining mid-stream is not
    staring at an empty dashboard until the next refresh tick, then only
    updates and heartbeats follow.
    """
    subscriber = streaming.subscribe(dashboard_id, user_id=caller)
    snapshot = await streaming.snapshot(dashboard_id, breakpoint_=breakpoint_, viewer_id=caller)
    heartbeat = request.app.state.service_settings.stream_heartbeat_seconds

    async def _frames() -> AsyncIterator[str]:
        yield snapshot.as_sse()
        try:
            async for event in streaming.stream(subscriber, heartbeat_seconds=heartbeat):
                yield event.as_sse()
        finally:
            streaming.unsubscribe(subscriber)

    return StreamingResponse(
        _frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.websocket("/{dashboard_id}/ws")
async def websocket_stream(websocket: WebSocket, dashboard_id: UUID) -> None:
    """Stream dashboard frames over a WebSocket.

    Authentication is the ``token`` query parameter rather than a header
    because browsers cannot set headers on a WebSocket handshake --
    the same constraint every WebSocket API faces. The token is verified
    with the same public key as every HTTP route; an invalid one closes
    the socket with policy-violation 1008 rather than serving frames.
    """
    token = websocket.query_params.get("token", "")
    try:
        claims = decode_token(token, public_key=websocket.app.state.jwt_public_key)
        user_id: UUID | None = UUID(str(claims["sub"]))
    except Exception:
        await websocket.close(code=1008, reason="Authentication required.")
        return

    hub = websocket.app.state.hub
    try:
        subscriber = hub.subscribe(dashboard_id, user_id=user_id)
    except RuntimeError as exc:
        await websocket.close(code=1013, reason=str(exc))
        return

    await websocket.accept()
    heartbeat = websocket.app.state.service_settings.stream_heartbeat_seconds
    try:
        await hub.publish_presence(dashboard_id)
        async for event in hub.stream(subscriber, heartbeat_seconds=heartbeat):
            await websocket.send_text(json.dumps(event.as_dict()))
    except WebSocketDisconnect:
        logger.debug(
            "A dashboard WebSocket disconnected.",
            extra={"extra_fields": {"dashboard_id": str(dashboard_id)}},
        )
    except Exception as exc:
        logger.warning(
            "A dashboard WebSocket failed.",
            extra={"extra_fields": {"dashboard_id": str(dashboard_id), "error": str(exc)}},
        )
    finally:
        hub.unsubscribe(subscriber)
        with contextlib.suppress(Exception):
            await hub.publish_presence(dashboard_id)
        with contextlib.suppress(Exception):
            await websocket.close()


@router.post(
    "/{dashboard_id}/refresh",
    response_model=SuccessResponse[dict[str, int]],
    summary="Push a refresh to live watchers",
)
async def refresh_now(
    dashboard_id: UUID, streaming: StreamingSvc, caller: CurrentUserId
) -> SuccessResponse[dict[str, int]]:
    """Tell everyone watching to re-fetch this dashboard now.

    Sends a nudge, not data. Each watcher re-fetches under their own
    token, which is what keeps one viewer's rights from leaking into
    another's view -- see :mod:`app.services.streaming`.
    """
    del caller  # authentication is the requirement
    delivered = await streaming.notify_stale(dashboard_id, reason="manual_refresh", force=True)
    return SuccessResponse(
        message=f"Refresh notice delivered to {delivered} watchers.",
        data={"delivered": delivered},
        meta=_meta(),
    )


__all__ = ["router"]
