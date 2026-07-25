"""Scheduler health.

Per docs/026_Enterprise_Scheduler_Framework.md.txt "HEALTH": Scheduler
Status, Worker Status, Leader Status, Queue Status, Heartbeat Status,
Cluster Health. Reuses :mod:`shared_core.monitoring.checks`/
:mod:`shared_core.monitoring.status` directly (already implement
dependency checks and worst-case status aggregation) rather than a
second health-check system -- this module only names the
scheduler-specific dimensions and folds them into one report via
:func:`shared_core.monitoring.status.calculate_status`.

"Database Connectivity" (also named in "HEALTH") is intentionally not a
field here: this framework (per its own "DIRECTORY STRUCTURE") has no
database layer of its own -- job state is in-process
(:mod:`shared_core.scheduler.registry`). Whatever service embeds this
framework and does own a database reports that dimension itself, via
:func:`shared_core.monitoring.checks.check_postgresql` directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from shared_core.enums.health_status import HealthStatus
from shared_core.enums.job_status import JobStatus
from shared_core.monitoring.checks import check_rabbitmq
from shared_core.monitoring.status import calculate_status
from shared_core.scheduler.heartbeat import HeartbeatRegistry
from shared_core.scheduler.leader import cluster_has_leader
from shared_core.scheduler.registry import JobRegistry

if TYPE_CHECKING:
    from aio_pika.abc import AbstractRobustConnection
    from redis.asyncio import Redis


@dataclass(frozen=True, slots=True)
class SchedulerHealthReport:
    """A point-in-time snapshot of every docs/026 "HEALTH" dimension this framework owns."""

    status: HealthStatus
    worker_status: HealthStatus
    leader_status: HealthStatus
    queue_status: HealthStatus
    heartbeat_status: HealthStatus
    active_worker_count: int
    registered_job_count: int
    running_job_count: int
    queue_error: str | None = None


def _worker_status(active_worker_count: int) -> HealthStatus:
    return HealthStatus.HEALTHY if active_worker_count > 0 else HealthStatus.UNHEALTHY


async def build_health_report(
    registry: JobRegistry,
    heartbeats: HeartbeatRegistry,
    redis_client: Redis,
    connection: AbstractRobustConnection,
) -> SchedulerHealthReport:
    """Build a full :class:`SchedulerHealthReport` ("Cluster Health")."""
    active_nodes = await heartbeats.list_active_nodes()
    active_worker_count = len(active_nodes)
    worker_status = _worker_status(active_worker_count)
    heartbeat_status = worker_status  # same underlying signal: live heartbeat presence

    has_leader = await cluster_has_leader(redis_client)
    leader_status = HealthStatus.HEALTHY if has_leader else HealthStatus.DEGRADED

    queue_check = await check_rabbitmq(connection)

    overall_status = calculate_status(
        [worker_status, leader_status, queue_check.status, heartbeat_status]
    )

    return SchedulerHealthReport(
        status=overall_status,
        worker_status=worker_status,
        leader_status=leader_status,
        queue_status=queue_check.status,
        heartbeat_status=heartbeat_status,
        active_worker_count=active_worker_count,
        registered_job_count=len(registry.list_jobs()),
        running_job_count=len(registry.list_by_status(JobStatus.RUNNING)),
        queue_error=queue_check.error,
    )


__all__ = ["SchedulerHealthReport", "build_health_report"]
