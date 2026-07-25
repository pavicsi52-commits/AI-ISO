"""Event replay.

Per docs/020_Enterprise_Event_Framework.md.txt "REPLAY": Replay by Time
Range, Organization, Project, Service, Event Type, Correlation ID.

RabbitMQ queues are FIFO with no historical-query support, so replay
needs its own queryable index. Backed by a bounded, self-trimming
Redis-based event log (:mod:`shared_core.cache`) rather than a database
table -- this indexes nothing but the EVENT FORMAT fields every event
already carries, so it's framework infrastructure, not a business record.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from redis.asyncio import Redis

from shared_core.cache.keys import build_cache_key
from shared_core.events.base import BaseEvent
from shared_core.events.constants import (
    DEFAULT_REPLAY_LIMIT,
    DEFAULT_REPLAY_RETENTION_SECONDS,
    MAX_REPLAY_LIMIT,
)
from shared_core.events.exceptions import EventReplayError
from shared_core.events.publisher import EventPublisher
from shared_core.events.registry import EventRegistry, default_registry
from shared_core.events.serializer import deserialize_event, serialize_event
from shared_core.helpers.json_helper import from_json, to_json


@dataclass(frozen=True, slots=True)
class ReplayCriteria:
    """Filters selecting which stored events a replay should re-publish."""

    start_time: datetime | None = None
    end_time: datetime | None = None
    organization_id: UUID | None = None
    project_id: UUID | None = None
    source_service: str | None = None
    event_name: str | None = None
    correlation_id: str | None = None
    limit: int = DEFAULT_REPLAY_LIMIT

    def matches(self, event: BaseEvent) -> bool:
        """Return whether *event* satisfies every filter set on this criteria."""
        checks = (
            self.start_time is None or event.timestamp >= self.start_time,
            self.end_time is None or event.timestamp <= self.end_time,
            self.organization_id is None or event.organization_id == self.organization_id,
            self.project_id is None or event.project_id == self.project_id,
            self.source_service is None or event.source_service == self.source_service,
            self.event_name is None or event.event_name == self.event_name,
            self.correlation_id is None or event.correlation_id == self.correlation_id,
        )
        return all(checks)


class EventStore:
    """A bounded, TTL-capped log of published events, queryable for replay.

    Backed directly by a Redis client's sorted-set + string commands
    (rather than :class:`shared_core.cache.manager.CacheManager`, whose
    higher-level API doesn't expose sorted sets) -- events are indexed by
    publish time in a single sorted set, trimmed to *retention_seconds* on
    every write, so the index self-cleans without a separate cron job.
    """

    def __init__(
        self, client: Redis, *, retention_seconds: int = DEFAULT_REPLAY_RETENTION_SECONDS
    ) -> None:
        self._client = client
        self._retention_seconds = retention_seconds

    def _event_key(self, event_id: UUID) -> str:
        return build_cache_key("event-store", "event", str(event_id))

    def _timeline_key(self) -> str:
        return build_cache_key("event-store", "timeline")

    async def append(self, event: BaseEvent) -> None:
        """Index *event* for later replay."""
        data = to_json(serialize_event(event)).encode("utf-8")
        await self._client.set(self._event_key(event.event_id), data, ex=self._retention_seconds)
        score = event.timestamp.timestamp()
        timeline_key = self._timeline_key()
        await self._client.zadd(timeline_key, {str(event.event_id): score})
        cutoff = score - self._retention_seconds
        await self._client.zremrangebyscore(timeline_key, "-inf", cutoff)

    async def query(
        self, criteria: ReplayCriteria, *, registry: EventRegistry = default_registry
    ) -> list[BaseEvent]:
        """Return every stored event matching *criteria*, oldest first."""
        min_score = criteria.start_time.timestamp() if criteria.start_time else "-inf"
        max_score = criteria.end_time.timestamp() if criteria.end_time else "+inf"
        limit = min(criteria.limit, MAX_REPLAY_LIMIT)

        event_ids = await self._client.zrangebyscore(
            self._timeline_key(), min_score, max_score, start=0, num=limit
        )
        results: list[BaseEvent] = []
        for raw_id in event_ids:
            event_id = str(raw_id.decode("utf-8") if isinstance(raw_id, bytes) else raw_id)
            data = await self._client.get(self._event_key(UUID(event_id)))
            if data is None:
                continue  # expired between the timeline lookup and this read
            event = deserialize_event(from_json(data), registry=registry)
            if criteria.matches(event):
                results.append(event)
        return results


async def replay_events(
    store: EventStore,
    publisher: EventPublisher,
    criteria: ReplayCriteria,
    *,
    registry: EventRegistry = default_registry,
) -> int:
    """Re-publish every stored event matching *criteria*. Returns the count replayed.

    Raises:
        EventReplayError: If the query or any re-publish fails.
    """
    try:
        events = await store.query(criteria, registry=registry)
        for event in events:
            await publisher.publish(event)
        return len(events)
    except Exception as exc:
        raise EventReplayError("Event replay failed.") from exc


__all__ = ["EventStore", "ReplayCriteria", "replay_events"]
