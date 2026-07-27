"""Repositories for the workflow runtime service's 18 tables."""

from __future__ import annotations

from app.repositories.workflow_approval import WorkflowApprovalRepository
from app.repositories.workflow_audit import WorkflowAuditEntryRepository
from app.repositories.workflow_checkpoint import WorkflowCheckpointRepository
from app.repositories.workflow_compensation import WorkflowCompensationRepository
from app.repositories.workflow_context import WorkflowContextEntryRepository
from app.repositories.workflow_definition import WorkflowDefinitionRepository
from app.repositories.workflow_event import WorkflowEventRecordRepository
from app.repositories.workflow_execution_step import WorkflowExecutionStepRepository
from app.repositories.workflow_instance import WorkflowInstanceRepository
from app.repositories.workflow_log import WorkflowLogRepository
from app.repositories.workflow_replay import WorkflowReplayRepository
from app.repositories.workflow_report import WorkflowReportRepository
from app.repositories.workflow_result import WorkflowResultRepository
from app.repositories.workflow_state import WorkflowStateTransitionRepository
from app.repositories.workflow_statistics import WorkflowStatisticsRepository
from app.repositories.workflow_timer import WorkflowTimerRepository
from app.repositories.workflow_variable import WorkflowVariableRepository
from app.repositories.workflow_version import WorkflowVersionRepository

__all__ = [
    "WorkflowApprovalRepository",
    "WorkflowAuditEntryRepository",
    "WorkflowCheckpointRepository",
    "WorkflowCompensationRepository",
    "WorkflowContextEntryRepository",
    "WorkflowDefinitionRepository",
    "WorkflowEventRecordRepository",
    "WorkflowExecutionStepRepository",
    "WorkflowInstanceRepository",
    "WorkflowLogRepository",
    "WorkflowReplayRepository",
    "WorkflowReportRepository",
    "WorkflowResultRepository",
    "WorkflowStateTransitionRepository",
    "WorkflowStatisticsRepository",
    "WorkflowTimerRepository",
    "WorkflowVariableRepository",
    "WorkflowVersionRepository",
]
