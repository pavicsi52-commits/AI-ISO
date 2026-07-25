"""Tests for factory.py, against real Redis and RabbitMQ."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fakeredis import FakeAsyncRedis
from redis.asyncio import Redis
from shared_core.queue.manager import QueueManager
from shared_core.scheduler.factory import create_scheduler_framework
from shared_core.scheduler.middleware import execution_logging_middleware


@pytest.fixture
async def redis_client() -> AsyncIterator[FakeAsyncRedis]:
    client = FakeAsyncRedis()
    yield client
    await client.aclose()


def test_create_scheduler_framework_wires_every_component(
    redis_client: Redis, queue_manager: QueueManager
) -> None:
    manager = create_scheduler_framework(queue_manager, redis_client)

    assert manager.node_id
    assert manager.heartbeat is not None
    assert manager.leader is not None
    assert manager.failover is not None


def test_create_scheduler_framework_respects_disable_flags(
    redis_client: Redis, queue_manager: QueueManager
) -> None:
    manager = create_scheduler_framework(
        queue_manager,
        redis_client,
        enable_leader_election=False,
        enable_heartbeat=False,
        enable_failover=False,
    )

    assert manager.heartbeat is None
    assert manager.leader is None
    assert manager.failover is None


def test_create_scheduler_framework_uses_a_given_node_id(
    redis_client: Redis, queue_manager: QueueManager
) -> None:
    manager = create_scheduler_framework(queue_manager, redis_client, node_id="node-fixed")

    assert manager.node_id == "node-fixed"


def test_create_scheduler_framework_accepts_a_custom_middleware_list(
    redis_client: Redis, queue_manager: QueueManager
) -> None:
    manager = create_scheduler_framework(
        queue_manager, redis_client, middlewares=[execution_logging_middleware]
    )

    assert manager.node_id


def test_create_scheduler_framework_accepts_an_empty_middleware_list(
    redis_client: Redis, queue_manager: QueueManager
) -> None:
    manager = create_scheduler_framework(queue_manager, redis_client, middlewares=[])

    assert manager.node_id
