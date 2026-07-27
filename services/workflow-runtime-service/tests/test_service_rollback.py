"""Tests for :class:`app.services.rollback.WorkflowRollbackService`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    CompensationStatus,
    NodeExecutionStatus,
    RollbackStatus,
    RollbackType,
)
from app.models.workflow_execution_step import WorkflowExecutionStep
from app.repositories.workflow_compensation import WorkflowCompensationRepository
from app.repositories.workflow_execution_step import WorkflowExecutionStepRepository
from app.repositories.workflow_instance import WorkflowInstanceRepository
from app.services.compensation import WorkflowCompensationService
from app.services.rollback import WorkflowRollbackService
from tests.conftest import (
    build_definition_service,
    build_version_service,
    make_definition,
    make_instance,
)


def _build_service(db_session: AsyncSession) -> WorkflowRollbackService:
    return WorkflowRollbackService(
        WorkflowInstanceRepository(db_session),
        WorkflowExecutionStepRepository(db_session),
        build_definition_service(db_session),
        build_version_service(db_session),
        WorkflowCompensationService(WorkflowCompensationRepository(db_session)),
    )


class TestWorkflowRollbackService:
    async def test_rollback_compensates_completed_task_nodes(
        self, db_session: AsyncSession
    ) -> None:
        nodes: list[dict[str, Any]] = [
            {"node_id": "start", "node_type": "start", "name": "start"},
            {"node_id": "task1", "node_type": "task", "name": "task1", "config": {"job_id": "j1"}},
            {"node_id": "end", "node_type": "end", "name": "end"},
        ]
        edges = [
            {"from_node_id": "start", "to_node_id": "task1"},
            {"from_node_id": "task1", "to_node_id": "end"},
        ]
        definition = await make_definition(db_session)
        version = await build_version_service(db_session).create_version(
            definition, nodes=nodes, edges=edges, current_version_number=None
        )
        instance = await make_instance(db_session, definition, version)

        steps = WorkflowExecutionStepRepository(db_session)
        await steps.create(
            WorkflowExecutionStep(
                organization_id=instance.organization_id,
                instance_id=instance.id,
                node_id="task1",
                node_type="task",
                status=NodeExecutionStatus.COMPLETED,
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                attempts=1,
            )
        )

        service = _build_service(db_session)
        status, compensated = await service.rollback(
            instance.id, node_ids=None, rollback_type=RollbackType.MANUAL
        )

        assert status == RollbackStatus.COMPLETED
        assert compensated == ["task1"]

        compensations = await WorkflowCompensationRepository(db_session).list_for_instance(
            instance.id
        )
        assert len(compensations) == 1
        assert compensations[0].status == CompensationStatus.COMPLETED

    async def test_rollback_with_no_completed_nodes_returns_failed_status(
        self, db_session: AsyncSession
    ) -> None:
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
        instance = await make_instance(db_session, definition, version)

        service = _build_service(db_session)
        status, compensated = await service.rollback(
            instance.id, node_ids=None, rollback_type=RollbackType.MANUAL
        )
        assert status == RollbackStatus.FAILED
        assert compensated == []
