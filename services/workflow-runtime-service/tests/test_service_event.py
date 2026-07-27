"""Tests for :class:`app.services.event.WorkflowEventService`."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow_instance import WorkflowInstance
from app.repositories.workflow_event import WorkflowEventRecordRepository
from app.services.event import WorkflowEventService
from tests.conftest import build_version_service, make_definition, make_instance


def _build_service(db_session: AsyncSession) -> WorkflowEventService:
    return WorkflowEventService(WorkflowEventRecordRepository(db_session))


async def _linear_instance(db_session: AsyncSession) -> WorkflowInstance:
    definition = await make_definition(db_session)
    version = await build_version_service(db_session).create_version(
        definition,
        nodes=[
            {"node_id": "start", "node_type": "start", "name": "start"},
            {"node_id": "end", "node_type": "end", "name": "end"},
        ],
        edges=[{"from_node_id": "start", "to_node_id": "end"}],
        current_version_number=None,
    )
    return await make_instance(db_session, definition, version)


class TestWorkflowEventService:
    async def test_record(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        record = await service.record(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            event_type="workflow.task.started",
            payload={"node_id": "task"},
            occurred_at=datetime.now(UTC),
        )
        assert record.event_type == "workflow.task.started"
        assert record.payload == {"node_id": "task"}

    async def test_list_for_instance_oldest_first(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        await service.record(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            event_type="workflow.started",
            payload={},
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        await service.record(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            event_type="workflow.completed",
            payload={},
            occurred_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
        events = await service.list_for_instance(instance.id)
        assert [event.event_type for event in events] == [
            "workflow.started",
            "workflow.completed",
        ]
