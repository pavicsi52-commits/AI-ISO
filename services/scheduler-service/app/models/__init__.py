"""Every table this service owns.

Imported as a package by Alembic's ``env.py``, which is what registers
each model with ``Base.metadata`` before autogenerate runs. A model not
re-exported here is a table the migration will not know about.
"""

from __future__ import annotations

from app.models.dependency import JobDependency
from app.models.execution import JobExecution, JobExecutionLog
from app.models.governance import SchedulerAudit, SchedulerReport, SchedulerStatistic
from app.models.history import JobFailure, JobHistory
from app.models.holiday import HolidayCalendarEntry
from app.models.job import ScheduledJob
from app.models.maintenance import MaintenanceWindow
from app.models.priority import JobPriorityPolicy
from app.models.retry import JobRetryPolicy
from app.models.trigger import JobSchedule, JobTrigger

__all__ = [
    "HolidayCalendarEntry",
    "JobDependency",
    "JobExecution",
    "JobExecutionLog",
    "JobFailure",
    "JobHistory",
    "JobPriorityPolicy",
    "JobRetryPolicy",
    "JobSchedule",
    "JobTrigger",
    "MaintenanceWindow",
    "ScheduledJob",
    "SchedulerAudit",
    "SchedulerReport",
    "SchedulerStatistic",
]
