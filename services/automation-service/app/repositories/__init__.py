"""Repositories for the automation service."""

from __future__ import annotations

from app.repositories.automation_approval import AutomationApprovalRepository
from app.repositories.automation_artifact import AutomationArtifactRepository
from app.repositories.automation_audit import AutomationAuditRepository
from app.repositories.automation_execution import AutomationExecutionRepository
from app.repositories.automation_execution_log import AutomationExecutionLogRepository
from app.repositories.automation_execution_plan import AutomationExecutionPlanRepository
from app.repositories.automation_execution_step import AutomationExecutionStepRepository
from app.repositories.automation_job import AutomationJobRepository
from app.repositories.automation_output import AutomationOutputRepository
from app.repositories.automation_parameter import AutomationParameterRepository
from app.repositories.automation_report import AutomationReportRepository
from app.repositories.automation_result import AutomationResultRepository
from app.repositories.automation_retry_history import AutomationRetryHistoryRepository
from app.repositories.automation_rollback import AutomationRollbackRepository
from app.repositories.automation_schedule import AutomationScheduleRepository
from app.repositories.automation_statistics import AutomationStatisticsRepository
from app.repositories.automation_target import AutomationTargetRepository
from app.repositories.automation_template import AutomationTemplateRepository
from app.repositories.automation_variable import AutomationVariableRepository

__all__ = [
    "AutomationApprovalRepository",
    "AutomationArtifactRepository",
    "AutomationAuditRepository",
    "AutomationExecutionLogRepository",
    "AutomationExecutionPlanRepository",
    "AutomationExecutionRepository",
    "AutomationExecutionStepRepository",
    "AutomationJobRepository",
    "AutomationOutputRepository",
    "AutomationParameterRepository",
    "AutomationReportRepository",
    "AutomationResultRepository",
    "AutomationRetryHistoryRepository",
    "AutomationRollbackRepository",
    "AutomationScheduleRepository",
    "AutomationStatisticsRepository",
    "AutomationTargetRepository",
    "AutomationTemplateRepository",
    "AutomationVariableRepository",
]
