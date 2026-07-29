"""The real-time hub ("REAL-TIME UPDATES").

One in-process hub owns every live subscriber. WebSocket and SSE are
two transports over the *same* hub rather than two parallel
implementations, so a fix to fan-out, presence, or back-pressure lands
in both at once.

**Slow subscribers are dropped, not waited on.** Each subscriber has a
bounded queue; when it fills, that subscriber is disconnected rather
than allowed to stall the publisher. A browser tab that has been
backgrounded for an hour must not hold up live updates for everyone
else looking at the same incident dashboard.

**Heartbeats are not decorative.** An idle WebSocket is
indistinguishable from a dead one, and intermediate proxies close
silent connections without telling either end. The heartbeat is what
turns "the dashboard stopped updating" into a detectable, recoverable
event -- which is exactly the "Connection Lost" case docs/048 asks to
notify on.

**Scope.** This hub is per-process. A multi-replica deployment needs a
shared broker so an update published on replica A reaches a subscriber
on replica B; :class:`DashboardHub` takes an optional *broadcaster* for
exactly that, and the Redis-backed one lives in
:mod:`app.realtime.broadcast`. Without it the hub still works
correctly, it simply only reaches subscribers on its own replica --
stated here rather than left for someone to discover in production.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from shared_core.logging.logger import get_logger

from app.models.enums import StreamEventKind

logger = get_logger("app.realtime.hub")

DEFAULT_QUEUE_SIZE = 64
"""Frames a subscriber may fall behind before being dropped.

Large enough to absorb a burst of widget updates, small enough that a
stalled client is noticed in seconds rather than consuming memory
indefinitely.
"""


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """One frame delivered to subscribers."""

    kind: StreamEventKind
    dashboard_id: UUID
    payload: dict[str, Any] = field(default_factory=dict)
    at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form."""
        return {
            "kind": str(self.kind),
            "dashboard_id": str(self.dashboard_id),
            "payload": self.payload,
            "at": self.at.isoformat(),
        }

    def as_sse(self) -> str:
        """This frame as a Server-Sent Events block."""
        return f"event: {self.kind}\ndata: {json.dumps(self.as_dict())}\n\n"


class Broadcaster(Protocol):
    """Cross-replica fan-out.

    Implemented by :class:`app.realtime.broadcast.RedisBroadcaster`; a
    single-replica deployment can run without one.
    """

    async def publish(self, event: StreamEvent) -> None:
        """Relay *event* to other replicas."""
        ...


@dataclass(slots=True)
class Subscriber:
    """One connected client."""

    subscriber_id: str
    dashboard_id: UUID
    user_id: UUID | None
    queue: asyncio.Queue[StreamEvent]
    connected_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_presence(self) -> dict[str, Any]:
        """This subscriber as a presence entry ("Presence Awareness")."""
        return {
            "subscriber_id": self.subscriber_id,
            "user_id": str(self.user_id) if self.user_id else None,
            "connected_at": self.connected_at.isoformat(),
        }


class DashboardHub:
    """Fan-out of dashboard updates to live subscribers."""

    def __init__(
        self,
        *,
        queue_size: int = DEFAULT_QUEUE_SIZE,
        max_subscribers: int = 500,
        broadcaster: Broadcaster | None = None,
    ) -> None:
        self._subscribers: dict[UUID, dict[str, Subscriber]] = {}
        self._queue_size = queue_size
        self._max_subscribers = max_subscribers
        self._broadcaster = broadcaster

    def attach_broadcaster(self, broadcaster: Broadcaster | None) -> None:
        """Attach cross-replica fan-out after construction.

        Needed because the broadcaster has to be told which hub to
        deliver into, so one of the two must exist first. Building the
        hub twice to work around that would leave the first one holding
        subscribers nothing ever delivers to.
        """
        self._broadcaster = broadcaster

    @property
    def subscriber_count(self) -> int:
        """How many clients are connected across every dashboard."""
        return sum(len(group) for group in self._subscribers.values())

    def count_for(self, dashboard_id: UUID) -> int:
        """How many clients are watching one dashboard."""
        return len(self._subscribers.get(dashboard_id, {}))

    def watched_dashboards(self) -> list[UUID]:
        """Every dashboard with at least one watcher on this replica.

        The refresh worker iterates this rather than every dashboard in
        the database, which is what keeps its cost proportional to the
        audience instead of to the size of the installation.
        """
        return [dashboard_id for dashboard_id, group in self._subscribers.items() if group]

    def presence(self, dashboard_id: UUID) -> list[dict[str, Any]]:
        """Who is currently watching one dashboard."""
        return [
            subscriber.as_presence()
            for subscriber in self._subscribers.get(dashboard_id, {}).values()
        ]

    def subscribe(self, dashboard_id: UUID, *, user_id: UUID | None = None) -> Subscriber:
        """Register a new subscriber.

        Raises:
            RuntimeError: If the deployment-wide subscriber ceiling is
                reached. Refusing a connection is far better than
                accepting one the process cannot serve.
        """
        if self.subscriber_count >= self._max_subscribers:
            raise RuntimeError(
                f"The real-time subscriber limit ({self._max_subscribers}) is reached."
            )
        subscriber = Subscriber(
            subscriber_id=uuid4().hex,
            dashboard_id=dashboard_id,
            user_id=user_id,
            queue=asyncio.Queue(maxsize=self._queue_size),
        )
        self._subscribers.setdefault(dashboard_id, {})[subscriber.subscriber_id] = subscriber
        return subscriber

    def unsubscribe(self, subscriber: Subscriber) -> None:
        """Remove a subscriber; safe to call twice."""
        group = self._subscribers.get(subscriber.dashboard_id)
        if group is None:
            return
        group.pop(subscriber.subscriber_id, None)
        if not group:
            self._subscribers.pop(subscriber.dashboard_id, None)

    async def publish(self, event: StreamEvent, *, relay: bool = True) -> int:
        """Deliver *event* to every local subscriber; returns how many.

        A subscriber whose queue is full is dropped rather than awaited:
        blocking here would let one stalled client freeze the update for
        everyone watching the same dashboard.
        """
        group = self._subscribers.get(event.dashboard_id, {})
        delivered = 0
        stalled: list[Subscriber] = []

        for subscriber in list(group.values()):
            try:
                subscriber.queue.put_nowait(event)
                delivered += 1
            except asyncio.QueueFull:
                stalled.append(subscriber)

        for subscriber in stalled:
            logger.warning(
                "Dropping a real-time subscriber that fell too far behind.",
                extra={
                    "extra_fields": {
                        "dashboard_id": str(event.dashboard_id),
                        "subscriber_id": subscriber.subscriber_id,
                    }
                },
            )
            self.unsubscribe(subscriber)

        if relay and self._broadcaster is not None:
            await self._broadcaster.publish(event)
        return delivered

    async def publish_update(
        self, dashboard_id: UUID, payload: dict[str, Any], *, relay: bool = True
    ) -> int:
        """Publish an incremental widget update."""
        return await self.publish(
            StreamEvent(kind=StreamEventKind.UPDATE, dashboard_id=dashboard_id, payload=payload),
            relay=relay,
        )

    async def publish_presence(self, dashboard_id: UUID) -> int:
        """Publish the current watcher list to everyone watching.

        Presence is never relayed cross-replica: each replica knows only
        its own connections, so relaying would let replicas overwrite
        each other with partial lists. A shared presence view needs the
        broadcaster to aggregate, which is a deliberate future step
        rather than something faked here.
        """
        return await self.publish(
            StreamEvent(
                kind=StreamEventKind.PRESENCE,
                dashboard_id=dashboard_id,
                payload={"watchers": self.presence(dashboard_id)},
            ),
            relay=False,
        )

    async def stream(
        self, subscriber: Subscriber, *, heartbeat_seconds: int = 20
    ) -> AsyncIterator[StreamEvent]:
        """Yield frames for one subscriber until it disconnects.

        Emits a heartbeat whenever the queue stays quiet, so a client
        can distinguish "nothing changed" from "the connection died"
        and reconnect on its own.
        """
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        subscriber.queue.get(), timeout=heartbeat_seconds
                    )
                except TimeoutError:
                    yield StreamEvent(
                        kind=StreamEventKind.HEARTBEAT,
                        dashboard_id=subscriber.dashboard_id,
                        payload={"subscriber_id": subscriber.subscriber_id},
                    )
                    continue
                yield event
        finally:
            self.unsubscribe(subscriber)

    async def close_all(self) -> None:
        """Drop every subscriber, for shutdown."""
        for group in list(self._subscribers.values()):
            for subscriber in list(group.values()):
                with contextlib.suppress(Exception):
                    self.unsubscribe(subscriber)
        self._subscribers.clear()


__all__ = [
    "DEFAULT_QUEUE_SIZE",
    "Broadcaster",
    "DashboardHub",
    "StreamEvent",
    "Subscriber",
]
