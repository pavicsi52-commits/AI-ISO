"""Every repository this service owns.

Each is tenant-scoped. The scoped lookups are named ``require_in_org``
rather than overriding the base ``require_by_id``: two same-named methods
of different arity on one class make an unscoped call look correct, which
is how a cross-tenant read gets written.
"""

from __future__ import annotations

from app.repositories.dependency import JobDependencyRepository
from app.repositories.execution import JobExecutionLogRepository, JobExecutionRepository
from app.repositories.governance import (
    SchedulerAuditRepository,
    SchedulerReportRepository,
    SchedulerStatisticRepository,
)
from app.repositories.history import JobFailureRepository, JobHistoryRepository
from app.repositories.holiday import HolidayCalendarRepository
from app.repositories.job import ScheduledJobRepository
from app.repositories.maintenance import MaintenanceWindowRepository
from app.repositories.priority import JobPriorityPolicyRepository
from app.repositories.retry import JobRetryPolicyRepository
from app.repositories.trigger import JobScheduleRepository, JobTriggerRepository

__all__ = [
    "HolidayCalendarRepository",
    "JobDependencyRepository",
    "JobExecutionLogRepository",
    "JobExecutionRepository",
    "JobFailureRepository",
    "JobHistoryRepository",
    "JobPriorityPolicyRepository",
    "JobRetryPolicyRepository",
    "JobScheduleRepository",
    "JobTriggerRepository",
    "MaintenanceWindowRepository",
    "ScheduledJobRepository",
    "SchedulerAuditRepository",
    "SchedulerReportRepository",
    "SchedulerStatisticRepository",
]
