"""Enterprise Scheduler Framework factory.

Assembles the registry, dependency graph, engine, queue, executor, and
every distributed-coordination piece into one
:class:`~shared_core.scheduler.manager.SchedulerManager` a service
builds exactly once at startup -- mirroring
:func:`shared_core.notifications.factory.create_notification_framework`
(Prompt 025) and :func:`shared_core.queue.factory.create_queue_framework`
(Prompt 021). Takes already-connected Redis/RabbitMQ clients rather than
building its own connections, since a service almost always shares one
connection pool across every framework that needs Redis/RabbitMQ.
"""

from __future__ import annotations

import logging

from redis.asyncio import Redis

from shared_core.queue.manager import QueueManager
from shared_core.scheduler.dependency import DependencyGraph
from shared_core.scheduler.engine import SchedulerEngine
from shared_core.scheduler.executor import JobExecutor
from shared_core.scheduler.failover import FailoverCoordinator
from shared_core.scheduler.heartbeat import HeartbeatRegistry, HeartbeatSender
from shared_core.scheduler.leader import LeaderElection
from shared_core.scheduler.manager import SchedulerManager, new_node_id
from shared_core.scheduler.middleware import (
    ExecuteMiddleware,
    apply_middleware,
    build_audit_middleware,
    correlation_id_middleware,
    error_handling_middleware,
    execution_logging_middleware,
    metrics_collection_middleware,
)
from shared_core.scheduler.queue import DEFAULT_JOB_QUEUE_NAME, JobQueue
from shared_core.scheduler.registry import JobRegistry

logger = logging.getLogger(__name__)


def _default_middlewares(node_id: str) -> list[ExecuteMiddleware]:
    """The baseline middleware chain: logging, correlation, audit, error handling, metrics.

    Deliberately excludes telemetry (needs a configured ``Tracer``) and
    security/tenant validation (need a caller-supplied policy callback,
    per docs/026 "DO NOT IMPLEMENT": Authentication) -- add those via
    :mod:`shared_core.scheduler.middleware` directly and pass the full
    list as *middlewares*.
    """
    return [
        execution_logging_middleware,
        correlation_id_middleware,
        build_audit_middleware(node_id),
        error_handling_middleware,
        metrics_collection_middleware,
    ]


async def _default_on_node_failed(failed_node_id: str) -> None:
    logger.warning(
        "Scheduler node %s stopped heartbeating; its in-flight jobs may need recovery.",
        failed_node_id,
    )


def create_scheduler_framework(
    queue_manager: QueueManager,
    redis_client: Redis,
    *,
    node_id: str | None = None,
    queue_name: str = DEFAULT_JOB_QUEUE_NAME,
    enable_leader_election: bool = True,
    enable_heartbeat: bool = True,
    enable_failover: bool = True,
    middlewares: list[ExecuteMiddleware] | None = None,
) -> SchedulerManager:
    """Build a fully-wired :class:`SchedulerManager` from real infrastructure connections.

    Pass ``middlewares=[]`` to run with no middleware chain at all, or a
    custom list to fully replace the default one (see
    :func:`_default_middlewares`).
    """
    resolved_node_id = node_id or new_node_id()
    registry = JobRegistry()
    engine = SchedulerEngine(registry, DependencyGraph())
    queue = JobQueue(queue_manager, queue_name=queue_name)
    executor = JobExecutor(lock_client=redis_client)

    chain = middlewares if middlewares is not None else _default_middlewares(resolved_node_id)
    handler = apply_middleware(executor.execute, chain) if chain else executor.execute

    heartbeat = (
        HeartbeatSender(HeartbeatRegistry(redis_client), resolved_node_id)
        if enable_heartbeat
        else None
    )
    leader = LeaderElection(redis_client, resolved_node_id) if enable_leader_election else None
    failover = (
        FailoverCoordinator(HeartbeatRegistry(redis_client), _default_on_node_failed)
        if enable_failover
        else None
    )

    return SchedulerManager(
        registry,
        engine,
        queue,
        executor,
        node_id=resolved_node_id,
        heartbeat=heartbeat,
        leader=leader,
        failover=failover,
        handler=handler,
    )


__all__ = ["create_scheduler_framework"]
