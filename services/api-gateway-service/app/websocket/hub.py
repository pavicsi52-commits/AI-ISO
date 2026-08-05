"""The WebSocket fan-out hub.

Structurally mirrors ``dashboard-service``'s own ``DashboardHub`` (the
established real-time precedent in this monorepo) -- same bounded-queue,
drop-the-slow-subscriber, heartbeat-on-idle design, keyed by
``organization_id`` instead of a dashboard id, since a gateway's own live
stream is naturally scoped to a tenant rather than to one dashboard.

**Per-process only.** Exactly like ``DashboardHub``, a subscriber only
receives events published on the same replica that accepted its
connection; a multi-replica deployment needs a shared broadcaster this
class does not implement, stated here rather than left to be discovered
in production.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from shared_core.logging.logger import get_logger

from app.models.enums import GatewayStreamEventKind

logger = get_logger("app.websocket.hub")

DEFAULT_QUEUE_SIZE = 64
"""Frames a subscriber may fall behind before being dropped."""


@dataclass(frozen=True, slots=True)
class GatewayStreamEvent:
    """One frame delivered to subscribers."""

    kind: GatewayStreamEventKind
    organization_id: UUID
    payload: dict[str, Any] = field(default_factory=dict)
    at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form."""
        return {
            "kind": str(self.kind),
            "organization_id": str(self.organization_id),
            "payload": self.payload,
            "at": self.at.isoformat(),
        }


@dataclass(slots=True)
class GatewaySubscriber:
    """One connected client."""

    subscriber_id: str
    organization_id: UUID
    user_id: UUID | None
    queue: asyncio.Queue[GatewayStreamEvent]
    connected_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class GatewayHub:
    """Fan-out of gateway events to live WebSocket subscribers."""

    def __init__(self, *, queue_size: int = DEFAULT_QUEUE_SIZE, max_subscribers: int = 500) -> None:
        self._subscribers: dict[UUID, dict[str, GatewaySubscriber]] = {}
        self._queue_size = queue_size
        self._max_subscribers = max_subscribers

    @property
    def subscriber_count(self) -> int:
        """How many clients are connected across every organization."""
        return sum(len(group) for group in self._subscribers.values())

    def count_for(self, organization_id: UUID) -> int:
        """How many clients are watching one organization's stream."""
        return len(self._subscribers.get(organization_id, {}))

    def subscribe(self, organization_id: UUID, *, user_id: UUID | None = None) -> GatewaySubscriber:
        """Register a new subscriber.

        Raises:
            RuntimeError: If the deployment-wide subscriber ceiling is reached.
        """
        if self.subscriber_count >= self._max_subscribers:
            raise RuntimeError(f"The real-time subscriber limit ({self._max_subscribers}) is reached.")
        subscriber = GatewaySubscriber(
            subscriber_id=uuid4().hex,
            organization_id=organization_id,
            user_id=user_id,
            queue=asyncio.Queue(maxsize=self._queue_size),
        )
        self._subscribers.setdefault(organization_id, {})[subscriber.subscriber_id] = subscriber
        return subscriber

    def unsubscribe(self, subscriber: GatewaySubscriber) -> None:
        """Remove a subscriber; safe to call twice."""
        group = self._subscribers.get(subscriber.organization_id)
        if group is None:
            return
        group.pop(subscriber.subscriber_id, None)
        if not group:
            self._subscribers.pop(subscriber.organization_id, None)

    async def publish(self, event: GatewayStreamEvent) -> int:
        """Deliver *event* to every local subscriber of its organization; returns how many.

        A subscriber whose queue is full is dropped rather than awaited.
        """
        group = self._subscribers.get(event.organization_id, {})
        delivered = 0
        stalled: list[GatewaySubscriber] = []

        for subscriber in list(group.values()):
            try:
                subscriber.queue.put_nowait(event)
                delivered += 1
            except asyncio.QueueFull:
                stalled.append(subscriber)

        for subscriber in stalled:
            logger.warning(
                "Dropping a gateway WebSocket subscriber that fell too far behind.",
                extra={
                    "extra_fields": {
                        "organization_id": str(event.organization_id),
                        "subscriber_id": subscriber.subscriber_id,
                    }
                },
            )
            self.unsubscribe(subscriber)
        return delivered

    async def stream(
        self, subscriber: GatewaySubscriber, *, heartbeat_seconds: int = 20
    ) -> AsyncIterator[GatewayStreamEvent]:
        """Yield frames for one subscriber until it disconnects.

        Emits a heartbeat whenever the queue stays quiet, so a client
        can distinguish "nothing changed" from "the connection died."
        """
        try:
            while True:
                try:
                    event = await asyncio.wait_for(subscriber.queue.get(), timeout=heartbeat_seconds)
                except TimeoutError:
                    yield GatewayStreamEvent(
                        kind=GatewayStreamEventKind.HEARTBEAT,
                        organization_id=subscriber.organization_id,
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


def frame_to_text(event: GatewayStreamEvent) -> str:
    """Render one frame as the JSON text sent over the wire."""
    return json.dumps(event.as_dict())


__all__ = [
    "DEFAULT_QUEUE_SIZE",
    "GatewayHub",
    "GatewayStreamEvent",
    "GatewaySubscriber",
    "frame_to_text",
]
