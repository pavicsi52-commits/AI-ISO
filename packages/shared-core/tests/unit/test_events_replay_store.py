"""Tests for the Redis-backed event store and replay-by-criteria, against
the real Redis started by the repository's docker-compose.yml.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import ClassVar

import pytest
from redis.asyncio import Redis
from shared_core.events.base import BaseEvent
from shared_core.events.exceptions import EventReplayError
from shared_core.events.publisher import EventPublisher
from shared_core.events.registry import EventRegistry
from shared_core.events.replay import EventStore, ReplayCriteria, replay_events


class _StockAdjusted(BaseEvent):
    event_name: ClassVar[str] = "stock.adjusted"


class _PriceChanged(BaseEvent):
    event_name: ClassVar[str] = "price.changed"


@pytest.fixture
def registry() -> EventRegistry:
    reg = EventRegistry()
    reg.register(_StockAdjusted)
    reg.register(_PriceChanged)
    return reg


class _RecordingPublisher:
    def __init__(self) -> None:
        self.published: list[BaseEvent] = []

    async def publish(self, event: BaseEvent) -> None:
        self.published.append(event)


async def test_append_and_query_round_trip(
    real_redis_client: Redis, registry: EventRegistry
) -> None:
    store = EventStore(real_redis_client)
    event = _StockAdjusted(source_service="inventory-service")

    await store.append(event)
    results = await store.query(ReplayCriteria(), registry=registry)

    assert len(results) == 1
    assert results[0].event_id == event.event_id
    assert isinstance(results[0], _StockAdjusted)


async def test_query_returns_events_oldest_first(
    real_redis_client: Redis, registry: EventRegistry
) -> None:
    store = EventStore(real_redis_client)
    older = _StockAdjusted(
        source_service="inventory-service", timestamp=datetime.now(UTC) - timedelta(seconds=30)
    )
    newer = _StockAdjusted(source_service="inventory-service", timestamp=datetime.now(UTC))

    await store.append(older)
    await store.append(newer)
    results = await store.query(ReplayCriteria(), registry=registry)

    assert [event.event_id for event in results] == [older.event_id, newer.event_id]


async def test_query_filters_by_organization_id(
    real_redis_client: Redis, registry: EventRegistry
) -> None:
    store = EventStore(real_redis_client)
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    event_a = _StockAdjusted(source_service="inventory-service", organization_id=org_a)
    event_b = _StockAdjusted(source_service="inventory-service", organization_id=org_b)
    await store.append(event_a)
    await store.append(event_b)

    results = await store.query(ReplayCriteria(organization_id=org_a), registry=registry)

    assert [event.event_id for event in results] == [event_a.event_id]


async def test_query_filters_by_event_name(
    real_redis_client: Redis, registry: EventRegistry
) -> None:
    store = EventStore(real_redis_client)
    stock_event = _StockAdjusted(source_service="inventory-service")
    price_event = _PriceChanged(source_service="pricing-service")
    await store.append(stock_event)
    await store.append(price_event)

    results = await store.query(ReplayCriteria(event_name="price.changed"), registry=registry)

    assert [event.event_id for event in results] == [price_event.event_id]


async def test_query_filters_by_correlation_id(
    real_redis_client: Redis, registry: EventRegistry
) -> None:
    store = EventStore(real_redis_client)
    matching = _StockAdjusted(source_service="inventory-service", correlation_id="corr-1")
    other = _StockAdjusted(source_service="inventory-service", correlation_id="corr-2")
    await store.append(matching)
    await store.append(other)

    results = await store.query(ReplayCriteria(correlation_id="corr-1"), registry=registry)

    assert [event.event_id for event in results] == [matching.event_id]


async def test_query_filters_by_time_range(
    real_redis_client: Redis, registry: EventRegistry
) -> None:
    store = EventStore(real_redis_client)
    now = datetime.now(UTC)
    too_old = _StockAdjusted(source_service="inventory-service", timestamp=now - timedelta(hours=2))
    in_range = _StockAdjusted(source_service="inventory-service", timestamp=now)
    await store.append(too_old)
    await store.append(in_range)

    results = await store.query(
        ReplayCriteria(start_time=now - timedelta(minutes=1), end_time=now + timedelta(minutes=1)),
        registry=registry,
    )

    assert [event.event_id for event in results] == [in_range.event_id]


async def test_query_respects_limit(real_redis_client: Redis, registry: EventRegistry) -> None:
    store = EventStore(real_redis_client)
    for _ in range(3):
        await store.append(_StockAdjusted(source_service="inventory-service"))

    results = await store.query(ReplayCriteria(limit=1), registry=registry)

    assert len(results) == 1


async def test_append_trims_events_older_than_retention(
    real_redis_client: Redis, registry: EventRegistry
) -> None:
    store = EventStore(real_redis_client, retention_seconds=10)
    now = datetime.now(UTC)
    ancient = _StockAdjusted(
        source_service="inventory-service", timestamp=now - timedelta(seconds=1000)
    )
    await store.append(ancient)

    # A fresh append's cutoff (now - retention_seconds) is well past `ancient`'s
    # score, so it gets trimmed out of the timeline immediately.
    recent = _StockAdjusted(source_service="inventory-service", timestamp=now)
    await store.append(recent)

    results = await store.query(ReplayCriteria(), registry=registry)

    assert [event.event_id for event in results] == [recent.event_id]


async def test_query_skips_a_timeline_entry_whose_data_key_already_expired(
    real_redis_client: Redis, registry: EventRegistry
) -> None:
    store = EventStore(real_redis_client)
    event = _StockAdjusted(source_service="inventory-service")
    await store.append(event)

    # Simulate the data key expiring (its own TTL) while the timeline entry
    # (only pruned on the next append) still references it.
    await real_redis_client.delete(store._event_key(event.event_id))

    results = await store.query(ReplayCriteria(), registry=registry)

    assert results == []


async def test_replay_events_republishes_every_matching_event(
    real_redis_client: Redis, registry: EventRegistry
) -> None:
    store = EventStore(real_redis_client)
    event = _StockAdjusted(source_service="inventory-service")
    await store.append(event)
    publisher = _RecordingPublisher()

    count = await replay_events(store, publisher, ReplayCriteria(), registry=registry)  # type: ignore[arg-type]

    assert count == 1
    assert publisher.published[0].event_id == event.event_id


async def test_replay_events_returns_zero_when_nothing_matches(
    real_redis_client: Redis, registry: EventRegistry
) -> None:
    store = EventStore(real_redis_client)
    publisher = _RecordingPublisher()

    count = await replay_events(
        store, publisher, ReplayCriteria(event_name="does.not.exist"), registry=registry  # type: ignore[arg-type]
    )

    assert count == 0
    assert publisher.published == []


async def test_replay_events_wraps_a_publish_failure(
    real_redis_client: Redis, registry: EventRegistry
) -> None:
    store = EventStore(real_redis_client)
    await store.append(_StockAdjusted(source_service="inventory-service"))

    class _FailingPublisher:
        async def publish(self, event: BaseEvent) -> None:
            raise ConnectionError("broker unreachable")

    with pytest.raises(EventReplayError):
        await replay_events(store, _FailingPublisher(), ReplayCriteria(), registry=registry)  # type: ignore[arg-type]


def test_event_publisher_satisfies_the_replay_publish_protocol() -> None:
    """EventPublisher itself is the real publisher replay_events is meant for."""
    assert hasattr(EventPublisher, "publish")
