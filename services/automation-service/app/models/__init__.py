"""SQLAlchemy models for the automation service.

Importing this package registers every table with
:data:`shared_core.database.base.Base.metadata`, required for Alembic
autogenerate.
"""

from __future__ import annotations

from app.models.automation_approval import AutomationApproval
from app.models.automation_artifact import AutomationArtifact
from app.models.automation_audit import AutomationAuditEntry
from app.models.automation_execution import AutomationExecution
from app.models.automation_execution_log import AutomationExecutionLog
from app.models.automation_execution_plan import AutomationExecutionPlan
from app.models.automation_execution_step import AutomationExecutionStep
from app.models.automation_job import AutomationJob
from app.models.automation_output import AutomationOutput
from app.models.automation_parameter import AutomationParameter
from app.models.automation_report import AutomationReport
from app.models.automation_result import AutomationResult
from app.models.automation_retry_history import AutomationRetryHistory
from app.models.automation_rollback import AutomationRollback
from app.models.automation_schedule import AutomationSchedule
from app.models.automation_statistics import AutomationStatistics
from app.models.automation_target import AutomationTarget
from app.models.automation_template import AutomationTemplate
from app.models.automation_variable import AutomationVariable

__all__ = [
    "AutomationApproval",
    "AutomationArtifact",
    "AutomationAuditEntry",
    "AutomationExecution",
    "AutomationExecutionLog",
    "AutomationExecutionPlan",
    "AutomationExecutionStep",
    "AutomationJob",
    "AutomationOutput",
    "AutomationParameter",
    "AutomationReport",
    "AutomationResult",
    "AutomationRetryHistory",
    "AutomationRollback",
    "AutomationSchedule",
    "AutomationStatistics",
    "AutomationTarget",
    "AutomationTemplate",
    "AutomationVariable",
]
