"""Tests for :class:`app.services.report.WorkflowReportService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.validation import ValidationError
from shared_core.workflow import NodeType
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    ApprovalDecisionStatus,
    WorkflowInstanceStatus,
    WorkflowReportType,
)
from app.models.workflow_instance import WorkflowInstance
from app.repositories.workflow_approval import WorkflowApprovalRepository
from app.repositories.workflow_checkpoint import WorkflowCheckpointRepository
from app.repositories.workflow_definition import WorkflowDefinitionRepository
from app.repositories.workflow_execution_step import WorkflowExecutionStepRepository
from app.repositories.workflow_instance import WorkflowInstanceRepository
from app.repositories.workflow_replay import WorkflowReplayRepository
from app.repositories.workflow_report import WorkflowReportRepository
from app.repositories.workflow_statistics import WorkflowStatisticsRepository
from app.services.approval import WorkflowApprovalService
from app.services.report import WorkflowReportService
from app.services.statistics import WorkflowStatisticsService
from tests.conftest import build_version_service, make_definition, make_instance


def _build_service(db_session: AsyncSession) -> WorkflowReportService:
    statistics = WorkflowStatisticsService(
        WorkflowStatisticsRepository(db_session),
        WorkflowDefinitionRepository(db_session),
        WorkflowInstanceRepository(db_session),
        WorkflowExecutionStepRepository(db_session),
        WorkflowApprovalRepository(db_session),
        WorkflowCheckpointRepository(db_session),
        WorkflowReplayRepository(db_session),
    )
    return WorkflowReportService(
        WorkflowReportRepository(db_session),
        WorkflowInstanceRepository(db_session),
        WorkflowExecutionStepRepository(db_session),
        WorkflowApprovalRepository(db_session),
        statistics,
    )


async def _linear_instance(
    db_session: AsyncSession, *, organization_id: uuid.UUID
) -> WorkflowInstance:
    definition = await make_definition(db_session, organization_id=organization_id)
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


class TestWorkflowReportService:
    async def test_generate_performance_report(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        service = _build_service(db_session)
        report = await service.generate(
            org_id,
            report_type=WorkflowReportType.PERFORMANCE,
            instance_id=None,
            definition_id=None,
            parameters={},
            generated_by=None,
        )
        assert "success_rate" in report.result

    async def test_generate_failure_report(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        instance = await _linear_instance(db_session, organization_id=org_id)
        instance.status = WorkflowInstanceStatus.FAILED
        await db_session.flush()

        service = _build_service(db_session)
        report = await service.generate(
            org_id,
            report_type=WorkflowReportType.FAILURE,
            instance_id=None,
            definition_id=None,
            parameters={},
            generated_by=None,
        )
        assert report.result["total_failed"] == 1

    async def test_generate_executive_dashboard_report(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        service = _build_service(db_session)
        report = await service.generate(
            org_id,
            report_type=WorkflowReportType.EXECUTIVE_DASHBOARD,
            instance_id=None,
            definition_id=None,
            parameters={},
            generated_by=None,
        )
        assert report.result["total_workflows"] == 0

    async def test_generate_workflow_history_report_requires_definition_id(
        self, db_session: AsyncSession
    ) -> None:
        service = _build_service(db_session)
        with pytest.raises(ValidationError):
            await service.generate(
                uuid.uuid4(),
                report_type=WorkflowReportType.WORKFLOW_HISTORY,
                instance_id=None,
                definition_id=None,
                parameters={},
                generated_by=None,
            )

    async def test_generate_workflow_history_report(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        instance = await _linear_instance(db_session, organization_id=org_id)
        service = _build_service(db_session)
        report = await service.generate(
            org_id,
            report_type=WorkflowReportType.WORKFLOW_HISTORY,
            instance_id=None,
            definition_id=instance.definition_id,
            parameters={},
            generated_by=None,
        )
        assert report.result["total_instances"] == 1

    async def test_generate_execution_report_requires_instance_id(
        self, db_session: AsyncSession
    ) -> None:
        service = _build_service(db_session)
        with pytest.raises(ValidationError):
            await service.generate(
                uuid.uuid4(),
                report_type=WorkflowReportType.EXECUTION,
                instance_id=None,
                definition_id=None,
                parameters={},
                generated_by=None,
            )

    async def test_generate_execution_report(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        instance = await _linear_instance(db_session, organization_id=org_id)
        service = _build_service(db_session)
        report = await service.generate(
            org_id,
            report_type=WorkflowReportType.EXECUTION,
            instance_id=instance.id,
            definition_id=None,
            parameters={},
            generated_by=None,
        )
        assert report.result["status"] == WorkflowInstanceStatus.QUEUED.value

    async def test_generate_approval_report(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        instance = await _linear_instance(db_session, organization_id=org_id)
        approvals = WorkflowApprovalService(WorkflowApprovalRepository(db_session))
        await approvals.request(
            organization_id=org_id,
            instance_id=instance.id,
            node_id="approval",
            node_type=NodeType.APPROVAL,
            approvers=["alice"],
        )
        service = _build_service(db_session)
        report = await service.generate(
            org_id,
            report_type=WorkflowReportType.APPROVAL,
            instance_id=instance.id,
            definition_id=None,
            parameters={},
            generated_by=None,
        )
        assert report.result["total_approvals"] == 1
        assert report.result["by_decision"] == {str(ApprovalDecisionStatus.PENDING): 1}

    async def test_list_for_org_and_for_instance(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        service = _build_service(db_session)
        await service.generate(
            org_id,
            report_type=WorkflowReportType.PERFORMANCE,
            instance_id=None,
            definition_id=None,
            parameters={},
            generated_by=None,
        )
        reports = await service.list_for_org(org_id)
        assert len(reports) == 1
        assert await service.list_for_org(org_id, report_type=WorkflowReportType.EXECUTION) == []
        assert await service.list_for_instance(uuid.uuid4()) == []
