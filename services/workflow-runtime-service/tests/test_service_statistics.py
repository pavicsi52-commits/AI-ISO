"""Tests for :class:`app.services.statistics.WorkflowStatisticsService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from shared_core.workflow import NodeType
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WorkflowInstanceStatus
from app.models.workflow_execution_step import WorkflowExecutionStep
from app.repositories.workflow_approval import WorkflowApprovalRepository
from app.repositories.workflow_checkpoint import WorkflowCheckpointRepository
from app.repositories.workflow_definition import WorkflowDefinitionRepository
from app.repositories.workflow_execution_step import WorkflowExecutionStepRepository
from app.repositories.workflow_instance import WorkflowInstanceRepository
from app.repositories.workflow_replay import WorkflowReplayRepository
from app.repositories.workflow_statistics import WorkflowStatisticsRepository
from app.services.statistics import WorkflowStatisticsService
from tests.conftest import build_version_service, make_definition, make_instance


def _build_service(db_session: AsyncSession) -> WorkflowStatisticsService:
    return WorkflowStatisticsService(
        WorkflowStatisticsRepository(db_session),
        WorkflowDefinitionRepository(db_session),
        WorkflowInstanceRepository(db_session),
        WorkflowExecutionStepRepository(db_session),
        WorkflowApprovalRepository(db_session),
        WorkflowCheckpointRepository(db_session),
        WorkflowReplayRepository(db_session),
    )


class TestWorkflowStatisticsService:
    async def test_recompute_with_no_data(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        service = _build_service(db_session)
        snapshot = await service.recompute(org_id)
        assert snapshot.total_workflows == 0
        assert snapshot.total_executions == 0
        assert snapshot.success_rate == 0.0

    async def test_recompute_counts_workflows_and_executions(
        self, db_session: AsyncSession
    ) -> None:
        org_id = uuid.uuid4()
        definition = await make_definition(db_session, organization_id=org_id)
        version = await build_version_service(db_session).create_version(
            definition,
            nodes=[
                {"node_id": "start", "node_type": "start", "name": "start"},
                {"node_id": "task", "node_type": "task", "name": "task"},
                {"node_id": "end", "node_type": "end", "name": "end"},
            ],
            edges=[
                {"from_node_id": "start", "to_node_id": "task"},
                {"from_node_id": "task", "to_node_id": "end"},
            ],
            current_version_number=None,
        )
        completed = await make_instance(
            db_session, definition, version, status=WorkflowInstanceStatus.COMPLETED
        )
        completed.started_at = datetime.now(UTC) - timedelta(seconds=10)
        completed.finished_at = datetime.now(UTC)
        failed = await make_instance(
            db_session, definition, version, status=WorkflowInstanceStatus.FAILED
        )
        failed.started_at = datetime.now(UTC) - timedelta(seconds=5)
        failed.finished_at = datetime.now(UTC)
        await db_session.flush()

        steps = WorkflowExecutionStepRepository(db_session)
        await steps.create(
            WorkflowExecutionStep(
                organization_id=org_id,
                instance_id=completed.id,
                node_id="task",
                node_type=NodeType.TASK,
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
            )
        )

        service = _build_service(db_session)
        snapshot = await service.recompute(org_id)

        assert snapshot.total_workflows == 1
        assert snapshot.total_executions == 2
        assert snapshot.success_rate == 0.5
        assert snapshot.failure_rate == 0.5
        assert snapshot.node_statistics.get(str(NodeType.TASK)) == 1

    async def test_get_for_org_recomputes_when_absent_then_returns_cached(
        self, db_session: AsyncSession
    ) -> None:
        org_id = uuid.uuid4()
        service = _build_service(db_session)
        first = await service.get_for_org(org_id)
        assert first.total_workflows == 0

        await make_definition(db_session, organization_id=org_id)
        cached = await service.get_for_org(org_id)
        assert cached.id == first.id
        assert cached.total_workflows == 0
