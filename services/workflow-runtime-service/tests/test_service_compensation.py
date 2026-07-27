"""Tests for :class:`app.services.compensation.WorkflowCompensationService`
and :func:`~app.services.compensation.build_compensation_registry`.
"""

from __future__ import annotations

import uuid

from shared_core.workflow import NodeType, WorkflowContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import CompensationStatus
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_version import WorkflowVersion
from app.repositories.workflow_compensation import WorkflowCompensationRepository
from app.services.compensation import WorkflowCompensationService, build_compensation_registry
from tests.conftest import build_version_service, make_definition, make_instance


def _build_service(db_session: AsyncSession) -> WorkflowCompensationService:
    return WorkflowCompensationService(WorkflowCompensationRepository(db_session))


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


class TestWorkflowCompensationService:
    async def test_record_succeeded(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        entry = await service.record_succeeded(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            node_id="task1",
            node_type=NodeType.TASK,
        )
        assert entry.status == CompensationStatus.COMPLETED
        assert entry.executed_at is not None

    async def test_record_failed(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        entry = await service.record_failed(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            node_id="task1",
            node_type=NodeType.TASK,
            error="boom",
        )
        assert entry.status == CompensationStatus.FAILED
        assert entry.error == "boom"

    async def test_list_for_instance(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        await service.record_succeeded(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            node_id="task1",
            node_type=NodeType.TASK,
        )
        entries = await service.list_for_instance(instance.id)
        assert len(entries) == 1


class TestBuildCompensationRegistry:
    def test_registers_only_task_and_connector_nodes(self, db_session: AsyncSession) -> None:
        instance = WorkflowInstance(
            organization_id=uuid.uuid4(),
            project_id=None,
            definition_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
        )
        version = WorkflowVersion(
            definition_id=uuid.uuid4(),
            version_number="1.0.0",
            nodes=[
                {"node_id": "start", "node_type": "start", "name": "start"},
                {"node_id": "task1", "node_type": "task", "name": "task1"},
                {"node_id": "conn1", "node_type": "connector", "name": "conn1"},
                {"node_id": "end", "node_type": "end", "name": "end"},
            ],
            edges=[],
            compiled_execution_plan=[],
        )
        service = _build_service(db_session)
        registry = build_compensation_registry(instance, version, service)

        assert registry.has_compensation("task1") is True
        assert registry.has_compensation("conn1") is True
        assert registry.has_compensation("start") is False
        assert registry.has_compensation("end") is False

    async def test_compensation_action_records_via_service(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        version = WorkflowVersion(
            definition_id=instance.definition_id,
            version_number="1.0.0",
            nodes=[{"node_id": "task1", "node_type": "task", "name": "task1"}],
            edges=[],
            compiled_execution_plan=[],
        )
        service = _build_service(db_session)
        registry = build_compensation_registry(instance, version, service)

        await registry.execute("task1", WorkflowContext(workflow_id="wf-1"))

        recorded = await service.list_for_instance(instance.id)
        assert len(recorded) == 1
        assert recorded[0].status == CompensationStatus.COMPLETED
