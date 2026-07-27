"""Tests for :class:`app.services.state.WorkflowStateTransitionService`."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WorkflowInstanceStatus
from app.models.workflow_instance import WorkflowInstance
from app.repositories.workflow_state import WorkflowStateTransitionRepository
from app.services.state import WorkflowStateTransitionService
from tests.conftest import build_version_service, make_definition, make_instance


def _build_service(db_session: AsyncSession) -> WorkflowStateTransitionService:
    return WorkflowStateTransitionService(WorkflowStateTransitionRepository(db_session))


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


class TestWorkflowStateTransitionService:
    async def test_record_transition(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        transition = await service.record(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            from_status=WorkflowInstanceStatus.QUEUED,
            to_status=WorkflowInstanceStatus.RUNNING,
        )
        assert transition.from_status == WorkflowInstanceStatus.QUEUED
        assert transition.to_status == WorkflowInstanceStatus.RUNNING

    async def test_record_initial_transition_with_no_from_status(
        self, db_session: AsyncSession
    ) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        transition = await service.record(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            from_status=None,
            to_status=WorkflowInstanceStatus.CREATED,
        )
        assert transition.from_status is None

    async def test_list_for_instance_oldest_first(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        await service.record(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            from_status=None,
            to_status=WorkflowInstanceStatus.CREATED,
        )
        await service.record(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            from_status=WorkflowInstanceStatus.CREATED,
            to_status=WorkflowInstanceStatus.QUEUED,
        )
        transitions = await service.list_for_instance(instance.id)
        assert [t.to_status for t in transitions] == [
            WorkflowInstanceStatus.CREATED,
            WorkflowInstanceStatus.QUEUED,
        ]
