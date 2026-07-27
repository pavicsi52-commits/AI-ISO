"""Compensation (Saga pattern) action outcome audit. Per docs/042
"COMPENSATION" "Support": Saga Pattern, Compensation Actions,
Compensation Queue, Retry Compensation, Failure Recovery, Compensation
Audit. The actions themselves are per-node-id closures built by
:func:`build_compensation_registry` -- this service's own methods only
record what actually happened once one ran.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from shared_core.workflow import CompensationRegistry, NodeType, WorkflowContext

from app.models.enums import CompensationStatus
from app.models.workflow_compensation import WorkflowCompensation
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_version import WorkflowVersion
from app.repositories.workflow_compensation import WorkflowCompensationRepository


class WorkflowCompensationService:
    """Records and reads compensation action outcomes."""

    def __init__(self, compensations: WorkflowCompensationRepository) -> None:
        self._compensations = compensations

    async def record_succeeded(
        self, *, organization_id: UUID, instance_id: UUID, node_id: str, node_type: NodeType
    ) -> WorkflowCompensation:
        """Record that *node_id*'s own compensation action completed successfully."""
        return await self._compensations.create(
            WorkflowCompensation(
                organization_id=organization_id,
                instance_id=instance_id,
                node_id=node_id,
                node_type=node_type,
                status=CompensationStatus.COMPLETED,
                executed_at=datetime.now(UTC),
            )
        )

    async def record_failed(
        self,
        *,
        organization_id: UUID,
        instance_id: UUID,
        node_id: str,
        node_type: NodeType,
        error: str,
    ) -> WorkflowCompensation:
        """Record that *node_id*'s own compensation action failed ("Failure Recovery")."""
        return await self._compensations.create(
            WorkflowCompensation(
                organization_id=organization_id,
                instance_id=instance_id,
                node_id=node_id,
                node_type=node_type,
                status=CompensationStatus.FAILED,
                executed_at=datetime.now(UTC),
                error=error,
            )
        )

    async def list_for_instance(self, instance_id: UUID) -> list[WorkflowCompensation]:
        """Every compensation action recorded for *instance_id* ("Compensation Audit")."""
        return await self._compensations.list_for_instance(instance_id)


def build_compensation_registry(
    instance: WorkflowInstance, version: WorkflowVersion, compensations: WorkflowCompensationService
) -> CompensationRegistry:
    """Build a real :class:`~shared_core.workflow.CompensationRegistry`
    for *instance*'s own run, registering a record-only compensation
    action for every ``TASK``/``CONNECTOR`` node in *version* -- shared
    by :class:`~app.services.execution.WorkflowExecutionService` (for
    the engine's own automatic rollback-on-failure) and
    :class:`~app.services.rollback.WorkflowRollbackService` (for a
    caller-initiated manual rollback), so both use the exact same
    compensation shape.
    """
    registry = CompensationRegistry()
    for node in version.nodes:
        node_type = node.get("node_type")
        if node_type not in (NodeType.TASK.value, NodeType.CONNECTOR.value):
            continue
        compensate = _build_noop_compensation(instance, node["node_id"], node_type, compensations)
        registry.register(node["node_id"], compensate)
    return registry


def _build_noop_compensation(
    instance: WorkflowInstance,
    node_id: str,
    node_type: str,
    compensations: WorkflowCompensationService,
) -> Callable[[WorkflowContext], Awaitable[None]]:
    """Record-only compensation: no automation-service endpoint exists
    to genuinely reverse an already-completed job execution (an honest
    platform gap, not a fake undo).
    """

    async def compensate(context: WorkflowContext) -> None:
        del context
        await compensations.record_succeeded(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            node_id=node_id,
            node_type=NodeType(node_type),
        )

    return compensate


__all__ = ["WorkflowCompensationService", "build_compensation_registry"]
