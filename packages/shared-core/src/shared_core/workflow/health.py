"""Workflow SDK health.

Per docs/028_Enterprise_Workflow_SDK.md.txt "DIRECTORY STRUCTURE"
(``health.py``; no dedicated content section elaborates it further).
Reuses :func:`shared_core.monitoring.checks.check_rabbitmq`/
:func:`shared_core.monitoring.status.calculate_status` (Prompt 023) for
queue connectivity and worst-case status rollup, matching
:mod:`shared_core.scheduler.health`'s identical pattern -- the workflow
runtime's own "Queue Integration" dependency is the same RabbitMQ this
checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from shared_core.enums.health_status import HealthStatus
from shared_core.monitoring.checks import check_rabbitmq
from shared_core.monitoring.status import calculate_status

if TYPE_CHECKING:
    from aio_pika.abc import AbstractRobustConnection


@dataclass(frozen=True, slots=True)
class WorkflowHealthReport:
    """A point-in-time snapshot of the workflow runtime's health."""

    status: HealthStatus
    queue_status: HealthStatus
    active_execution_count: int
    registered_workflow_count: int
    queue_error: str | None = None


async def build_health_report(
    connection: AbstractRobustConnection,
    *,
    active_execution_count: int,
    registered_workflow_count: int,
) -> WorkflowHealthReport:
    """Build a full :class:`WorkflowHealthReport`."""
    queue_check = await check_rabbitmq(connection)
    overall_status = calculate_status([queue_check.status])
    return WorkflowHealthReport(
        status=overall_status,
        queue_status=queue_check.status,
        active_execution_count=active_execution_count,
        registered_workflow_count=registered_workflow_count,
        queue_error=queue_check.error,
    )


__all__ = ["WorkflowHealthReport", "build_health_report"]
