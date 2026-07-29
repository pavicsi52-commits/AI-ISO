"""Cross-replica fan-out over Redis pub/sub.

:class:`~app.realtime.hub.DashboardHub` is per-process, so an update
published on replica A never reaches a subscriber connected to replica
B. This relays events between replicas so a horizontally scaled
deployment behaves like a single one.

**Redis pub/sub is fire-and-forget, and that is the right trade here.**
A dashboard frame is worth delivering *now* or not at all: a widget
value that arrives thirty seconds late after a broker replay is worse
than one the client re-fetches on its next refresh. Durable delivery
would mean per-subscriber queues surviving disconnects, which is a
mailbox, not a live view.

**A relayed event is never re-relayed.** Publishing with ``relay=False``
on receipt is what stops two replicas bouncing the same frame between
each other forever.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from shared_core.logging.logger import get_logger

from app.models.enums import StreamEventKind
from app.realtime.hub import DashboardHub, StreamEvent

logger = get_logger("app.realtime.broadcast")

CHANNEL = "aiios:dashboard:events"
"""The single pub/sub channel every replica subscribes to.

One channel rather than one per dashboard: Redis pattern subscriptions
across thousands of dashboards cost more than filtering a small
payload locally, and the hub already discards events for dashboards it
has no subscribers for.
"""


def encode(event: StreamEvent) -> str:
    """Serialise an event for the wire."""
    return json.dumps(event.as_dict())


def decode(raw: str | bytes) -> StreamEvent | None:
    """Parse a relayed event, or ``None`` if it is unusable.

    A malformed frame from another replica is dropped with a warning
    rather than raising: one bad message must not tear down the
    listener that every live dashboard on this replica depends on.
    """
    try:
        payload = json.loads(raw)
        return StreamEvent(
            kind=StreamEventKind(payload["kind"]),
            dashboard_id=UUID(payload["dashboard_id"]),
            payload=dict(payload.get("payload") or {}),
            at=datetime.fromisoformat(payload["at"]),
        )
    except Exception as exc:
        logger.warning(
            "Discarding a malformed relayed dashboard event.",
            extra={"extra_fields": {"error": str(exc)}},
        )
        return None


class RedisBroadcaster:
    """Relays dashboard events between replicas."""

    def __init__(self, client: Redis, hub: DashboardHub, *, channel: str = CHANNEL) -> None:
        self._client = client
        self._hub = hub
        self._channel = channel
        self._task: asyncio.Task[None] | None = None

    async def publish(self, event: StreamEvent) -> None:
        """Relay one event to the other replicas.

        A publish failure is logged, never raised: the local subscribers
        have already been served, and failing the originating request
        because a *remote* fan-out hiccupped would be the wrong trade.
        """
        try:
            await self._client.publish(self._channel, encode(event))
        except Exception as exc:
            logger.warning(
                "Could not relay a dashboard event to other replicas.",
                extra={"extra_fields": {"error": str(exc)}},
            )

    async def start(self) -> None:
        """Begin listening for events from other replicas."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        """Stop listening."""
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _listen(self) -> None:
        """Consume relayed events until cancelled."""
        # Annotated Any because redis-py ships PubSub only partially
        # typed -- ``aclose`` has no annotations, so calling it through
        # the precise type is a mypy error about the library, not about
        # this code.
        pubsub: Any = self._client.pubsub()
        try:
            await pubsub.subscribe(self._channel)
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                event = decode(message["data"])
                if event is not None:
                    # relay=False: this frame already came from another
                    # replica, so re-publishing it would loop forever.
                    await self._hub.publish(event, relay=False)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "The dashboard event listener stopped; this replica will "
                "only serve locally published updates.",
                extra={"extra_fields": {"error": str(exc)}},
            )
        finally:
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe(self._channel)
                await pubsub.aclose()


def build_broadcaster(client: Any | None, hub: DashboardHub) -> RedisBroadcaster | None:
    """Build a broadcaster, or ``None`` when Redis is unavailable.

    ``None`` is not a failure: the hub still serves every subscriber on
    this replica. It only means cross-replica relay is off, which a
    single-replica deployment never needed.
    """
    if client is None:
        return None
    return RedisBroadcaster(client, hub)


__all__ = ["CHANNEL", "RedisBroadcaster", "build_broadcaster", "decode", "encode"]
