"""Tests for locking.py, leader.py, heartbeat.py, and failover.py."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from fakeredis import FakeAsyncRedis
from redis.asyncio import Redis
from shared_core.scheduler.failover import FailoverCoordinator
from shared_core.scheduler.heartbeat import HeartbeatRegistry, HeartbeatSender
from shared_core.scheduler.leader import LeaderElection
from shared_core.scheduler.locking import exclusive_job_execution, job_lock_key


@pytest.fixture
async def redis_client() -> AsyncIterator[FakeAsyncRedis]:
    client = FakeAsyncRedis()
    yield client
    await client.aclose()


# --- locking.py ---


def test_job_lock_key_is_namespaced_by_job_id() -> None:
    assert job_lock_key("job-1") == "scheduler:job-lock:job-1"


async def test_exclusive_job_execution_grants_the_lock_when_free(redis_client: Redis) -> None:
    async with exclusive_job_execution(redis_client, "job-1") as acquired:
        assert acquired is True


async def test_exclusive_job_execution_releases_on_exit(redis_client: Redis) -> None:
    async with exclusive_job_execution(redis_client, "job-1"):
        pass

    assert await redis_client.exists(job_lock_key("job-1")) == 0


async def test_exclusive_job_execution_denies_a_second_concurrent_holder(
    redis_client: Redis,
) -> None:
    async with exclusive_job_execution(redis_client, "job-1") as first:
        assert first is True
        async with exclusive_job_execution(redis_client, "job-1") as second:
            assert second is False


# --- leader.py ---


async def test_leader_election_campaign_grants_leadership_when_uncontested(
    redis_client: Redis,
) -> None:
    election = LeaderElection(redis_client, "node-a")

    assert await election.campaign() is True
    assert election.is_leader is True


async def test_leader_election_only_one_node_wins(redis_client: Redis) -> None:
    node_a = LeaderElection(redis_client, "node-a")
    node_b = LeaderElection(redis_client, "node-b")

    assert await node_a.campaign() is True
    assert await node_b.campaign() is False
    assert node_b.is_leader is False


async def test_leader_election_incumbent_keeps_renewing(redis_client: Redis) -> None:
    election = LeaderElection(redis_client, "node-a")
    await election.campaign()

    assert await election.campaign() is True
    assert election.is_leader is True


async def test_leader_election_resign_releases_the_lock(redis_client: Redis) -> None:
    node_a = LeaderElection(redis_client, "node-a")
    node_b = LeaderElection(redis_client, "node-b")
    await node_a.campaign()

    await node_a.resign()

    assert node_a.is_leader is False
    assert await node_b.campaign() is True


async def test_leader_election_start_stop_lifecycle(redis_client: Redis) -> None:
    election = LeaderElection(redis_client, "node-a", renew_interval_seconds=0.01)

    await election.start()
    try:
        await asyncio.sleep(0.05)
        assert election.is_leader is True
    finally:
        await election.stop()

    assert election.is_leader is False


async def test_leader_election_start_is_idempotent(redis_client: Redis) -> None:
    election = LeaderElection(redis_client, "node-a", renew_interval_seconds=0.01)

    await election.start()
    await election.start()
    await election.stop()


# --- heartbeat.py ---


async def test_heartbeat_registry_beat_then_is_alive(redis_client: Redis) -> None:
    registry = HeartbeatRegistry(redis_client)

    await registry.beat("node-a")

    assert await registry.is_alive("node-a") is True


async def test_heartbeat_registry_unknown_node_is_not_alive(redis_client: Redis) -> None:
    registry = HeartbeatRegistry(redis_client)

    assert await registry.is_alive("ghost") is False


async def test_heartbeat_registry_deregister_removes_the_node(redis_client: Redis) -> None:
    registry = HeartbeatRegistry(redis_client)
    await registry.beat("node-a")

    await registry.deregister("node-a")

    assert await registry.is_alive("node-a") is False


async def test_heartbeat_registry_lists_every_active_node(redis_client: Redis) -> None:
    registry = HeartbeatRegistry(redis_client)
    await registry.beat("node-a")
    await registry.beat("node-b")

    nodes = await registry.list_active_nodes()

    assert {node.node_id for node in nodes} == {"node-a", "node-b"}


async def test_heartbeat_sender_beats_immediately_on_start(redis_client: Redis) -> None:
    registry = HeartbeatRegistry(redis_client)
    sender = HeartbeatSender(registry, "node-a", interval_seconds=10)

    await sender.start()
    try:
        assert await registry.is_alive("node-a") is True
    finally:
        await sender.stop()


async def test_heartbeat_sender_stop_deregisters(redis_client: Redis) -> None:
    registry = HeartbeatRegistry(redis_client)
    sender = HeartbeatSender(registry, "node-a", interval_seconds=10)
    await sender.start()

    await sender.stop()

    assert await registry.is_alive("node-a") is False


async def test_heartbeat_sender_start_is_idempotent(redis_client: Redis) -> None:
    registry = HeartbeatRegistry(redis_client)
    sender = HeartbeatSender(registry, "node-a", interval_seconds=10)

    await sender.start()
    await sender.start()
    await sender.stop()


# --- failover.py ---


async def test_failover_coordinator_check_once_detects_a_dead_node(redis_client: Redis) -> None:
    registry = HeartbeatRegistry(redis_client)
    await registry.beat("node-a")
    await registry.beat("node-b")
    failed: list[str] = []

    async def on_node_failed(node_id: str) -> None:
        failed.append(node_id)

    coordinator = FailoverCoordinator(registry, on_node_failed)
    await coordinator.start()
    await registry.deregister("node-b")

    result = await coordinator.check_once()

    assert result == ["node-b"]
    assert failed == ["node-b"]
    await coordinator.stop()


async def test_failover_coordinator_does_not_refire_for_the_same_failure(
    redis_client: Redis,
) -> None:
    registry = HeartbeatRegistry(redis_client)
    await registry.beat("node-a")
    call_count = 0

    async def on_node_failed(_node_id: str) -> None:
        nonlocal call_count
        call_count += 1

    coordinator = FailoverCoordinator(registry, on_node_failed)
    await coordinator.start()
    await registry.deregister("node-a")

    await coordinator.check_once()
    await coordinator.check_once()

    assert call_count == 1
    await coordinator.stop()


async def test_failover_coordinator_swallows_a_callback_exception(redis_client: Redis) -> None:
    registry = HeartbeatRegistry(redis_client)
    await registry.beat("node-a")

    async def on_node_failed(_node_id: str) -> None:
        raise RuntimeError("recovery blew up")

    coordinator = FailoverCoordinator(registry, on_node_failed)
    await coordinator.start()
    await registry.deregister("node-a")

    result = await coordinator.check_once()  # must not raise

    assert result == ["node-a"]
    await coordinator.stop()


async def test_failover_coordinator_stop_is_safe_when_never_started(redis_client: Redis) -> None:
    registry = HeartbeatRegistry(redis_client)

    async def on_node_failed(_node_id: str) -> None:
        pass

    coordinator = FailoverCoordinator(registry, on_node_failed)

    await coordinator.stop()
