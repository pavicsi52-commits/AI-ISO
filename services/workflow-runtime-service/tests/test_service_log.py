"""Tests for :class:`app.services.log.WorkflowLogService`."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow_instance import WorkflowInstance
from app.repositories.workflow_log import WorkflowLogRepository
from app.services.log import WorkflowLogService
from tests.conftest import build_version_service, make_definition, make_instance


def _build_service(db_session: AsyncSession) -> WorkflowLogService:
    return WorkflowLogService(WorkflowLogRepository(db_session))


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


class TestWorkflowLogService:
    async def test_record_with_defaults(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        log = await service.record(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            message="node started",
        )
        assert log.level == "info"
        assert log.node_id is None

    async def test_record_with_node_and_level(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        log = await service.record(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            message="node failed",
            level="error",
            node_id="task",
        )
        assert log.level == "error"
        assert log.node_id == "task"

    async def test_list_for_instance_oldest_first(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        await service.record(
            organization_id=instance.organization_id, instance_id=instance.id, message="first"
        )
        await service.record(
            organization_id=instance.organization_id, instance_id=instance.id, message="second"
        )
        logs = await service.list_for_instance(instance.id)
        assert [log.message for log in logs] == ["first", "second"]
