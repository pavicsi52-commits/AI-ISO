"""Integration flow management (docs/058 "INTEGRATION FLOWS")."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.events.hub_events import SOURCE_SERVICE, FlowExecutedEvent
from app.flows.engine import FlowEngine, FlowRunResult
from app.models.enums import EventSource, FlowRunStatus, FlowStatus, FlowTrigger
from app.models.flow import ConnectorFlow
from app.repositories.flow import ConnectorFlowRepository
from app.services.event import EventService
from app.services.sync import SyncService
from app.services.transformation import TransformationService
from app.types import EventPublisher


class FlowService:
    """Creates flow definitions and runs them through :class:`~app.flows.engine.FlowEngine`.

    Binds the engine's own ``action`` steps to this service's real
    collaborators: ``"sync"`` triggers and runs a sync job,
    ``"transform"`` applies a connector's own transformations to
    ``context["record"]``, ``"route_event"`` ingests and routes an
    event, ``"noop"`` does nothing (useful for a flow step that only
    exists to gate on a condition/approval). An unrecognised action name
    raises, the same as any other step failure the engine's own retry/
    compensation handling already covers.
    """

    def __init__(
        self,
        flows: ConnectorFlowRepository,
        sync: SyncService,
        transformations: TransformationService,
        events: EventService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._flows = flows
        self._sync = sync
        self._transformations = transformations
        self._events = events
        self._publish = publish_event

    async def create(
        self,
        organization_id: UUID,
        *,
        name: str,
        definition: dict[str, Any],
        connector_id: UUID | None = None,
        description: str | None = None,
        trigger: FlowTrigger = FlowTrigger.MANUAL,
        schedule_interval_seconds: int | None = None,
    ) -> ConnectorFlow:
        """Register a new flow definition, in ``DRAFT``."""
        return await self._flows.create(
            ConnectorFlow(
                organization_id=organization_id,
                connector_id=connector_id,
                name=name,
                description=description,
                definition=definition,
                trigger=trigger,
                schedule_interval_seconds=schedule_interval_seconds,
                status=FlowStatus.DRAFT,
            )
        )

    async def get(self, organization_id: UUID, flow_id: UUID) -> ConnectorFlow:
        """One flow.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._flows.require_in_org(organization_id, flow_id)

    async def list_for_org(
        self, organization_id: UUID, *, enabled: bool | None = None
    ) -> list[ConnectorFlow]:
        """Flows in this organization."""
        return await self._flows.list_for_org(organization_id, enabled=enabled)

    async def activate(self, organization_id: UUID, flow_id: UUID) -> ConnectorFlow:
        """Move a flow into ``ACTIVE`` and make it eligible to run."""
        flow = await self.get(organization_id, flow_id)
        flow.status = FlowStatus.ACTIVE
        flow.enabled = True
        return await self._flows.update(flow)

    async def disable(self, organization_id: UUID, flow_id: UUID) -> ConnectorFlow:
        """Disable a flow."""
        flow = await self.get(organization_id, flow_id)
        flow.enabled = False
        flow.status = FlowStatus.DISABLED
        return await self._flows.update(flow)

    async def run(
        self, organization_id: UUID, flow: ConnectorFlow, *, context: dict[str, Any] | None = None
    ) -> FlowRunResult:
        """Execute *flow*'s own definition.

        Raises:
            ValidationError: If *flow* is not currently active.
        """
        if flow.status != FlowStatus.ACTIVE:
            raise ValidationError(f"Flow {flow.id} is not active (status={flow.status!s}).")

        engine = FlowEngine(executor=self._execute_step)
        result = await engine.run(flow.definition, context=context)

        flow.run_count += 1
        flow.last_run_at = datetime.now(UTC)
        flow.last_run_status = FlowRunStatus(result.status)
        flow.last_error = result.error
        await self._flows.update(flow)

        await self._publish_event(
            FlowExecutedEvent(
                source_service=SOURCE_SERVICE,
                organization_id=organization_id,
                payload={
                    "flow_id": str(flow.id),
                    "status": result.status,
                    "steps": result.steps_executed,
                },
            )
        )
        return result

    async def _execute_step(
        self, action: str, config: Mapping[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        if action == "noop":
            return {}
        if action == "sync":
            organization_id = UUID(str(context["organization_id"]))
            connector_id = UUID(str(config.get("connector_id") or context.get("connector_id")))
            job = await self._sync.trigger(
                organization_id, connector_id=connector_id, triggered_by="flow"
            )
            job = await self._sync.run(organization_id, job, records=context.get("records", []))
            return {"sync_job_id": str(job.id), "sync_status": str(job.status)}
        if action == "transform":
            connector_id = UUID(str(config.get("connector_id") or context.get("connector_id")))
            record = context.get("record", {})
            return {"record": await self._transformations.apply_all(connector_id, record)}
        if action == "route_event":
            connector_ref = config.get("connector_id") or context.get("connector_id")
            organization_id = UUID(str(context["organization_id"]))
            event = await self._events.ingest(
                organization_id,
                connector_id=UUID(str(connector_ref)) if connector_ref else None,
                source=EventSource(context.get("source", EventSource.INTERNAL)),
                event_type=str(config.get("event_type", "flow.step")),
                payload=context.get("record", {}),
                routes=config.get("routes", []),
            )
            return {"event_id": str(event.id)}
        raise ValueError(f"Unrecognised flow action: {action!r}")

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)


__all__ = ["FlowService"]
