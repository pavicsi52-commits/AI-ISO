"""The platform's fixed scheduler vocabulary (docs/054).

Every ``Mapped[SomeEnum]`` column below is backed by ``String`` at the
database layer, per this repository's established SQLAlchemy 2.0
pattern: a raw string round-trips through Postgres exactly, unlike a
native ``ENUM`` type, which turns every new member into a migration
against a type the whole cluster shares. The cost is that a value freshly
loaded from the database is a plain ``str``, not the enum member -- so
every column that is ever compared, branched on, or handed to another
enum-typed field carries an ``X_of()`` normaliser here, and application
code calls it on the *column*, never on the record that owns it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class JobType(StrEnum):
    """What kind of work a scheduled job dispatches (docs/054 "JOB TYPES").

    This service never performs the work itself -- see this package's
    own README for why -- only tracks that a trigger fired and dispatched
    to whichever platform service owns the type."""

    AUTOMATION_JOB = "automation_job"
    WORKFLOW_JOB = "workflow_job"
    VALIDATION_JOB = "validation_job"
    MONITORING_JOB = "monitoring_job"
    COMPLIANCE_SCAN = "compliance_scan"
    DISCOVERY_JOB = "discovery_job"
    INVENTORY_SYNC = "inventory_sync"
    BACKUP_JOB = "backup_job"
    REPORT_GENERATION = "report_generation"
    NOTIFICATION_JOB = "notification_job"
    AI_TASK = "ai_task"
    CLEANUP_JOB = "cleanup_job"
    MAINTENANCE_JOB = "maintenance_job"
    WEBHOOK_JOB = "webhook_job"
    CUSTOM_JOB = "custom_job"


class ScheduleType(StrEnum):
    """How a job's own trigger decides when it is due (docs/054 "SCHEDULE TYPES")."""

    ONE_TIME = "one_time"
    RECURRING = "recurring"
    CRON = "cron"
    INTERVAL = "interval"
    CALENDAR = "calendar"
    EVENT_DRIVEN = "event_driven"
    DEPENDENCY_DRIVEN = "dependency_driven"
    MANUAL_TRIGGER = "manual_trigger"
    MAINTENANCE_WINDOW = "maintenance_window"
    CUSTOM_SCHEDULE = "custom_schedule"


class ScheduledJobStatus(StrEnum):
    """A job *definition's* own lifecycle -- distinct from any one run's status."""

    REGISTERED = "registered"
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    DELETED = "deleted"


class ExecutionStatus(StrEnum):
    """One run's own status (docs/054 "EXECUTION MANAGEMENT")."""

    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    SKIPPED = "skipped"
    WAITING = "waiting"
    BLOCKED = "blocked"
    RECOVERED = "recovered"


class JobPriority(StrEnum):
    """How urgently a job's execution should be dispatched relative to others."""

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    BACKGROUND = "background"


class RetryType(StrEnum):
    """How the delay between retry attempts grows."""

    FIXED = "fixed"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"
    CUSTOM = "custom"


class DependencyType(StrEnum):
    """How a child job's execution relates to its parent's."""

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"


class DependencyCondition(StrEnum):
    """For a ``CONDITIONAL`` dependency, which of the parent's outcomes satisfies it."""

    ON_SUCCESS = "on_success"
    ON_FAILURE = "on_failure"
    ON_COMPLETION = "on_completion"


class CalendarRuleKind(StrEnum):
    """The recurrence a ``CALENDAR``-type trigger, maintenance window, or
    holiday follows. ``NONE`` is only meaningful for a maintenance
    window or holiday exception -- a ``CALENDAR``-type job trigger is by
    definition recurring, so it never uses ``NONE`` itself."""

    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    BUSINESS_DAYS = "business_days"
    WEEKENDS = "weekends"
    CUSTOM = "custom"


class MaintenanceWindowScope(StrEnum):
    """What a maintenance window applies to."""

    GLOBAL = "global"
    ORGANIZATION = "organization"
    PROJECT = "project"
    ENVIRONMENT = "environment"
    ASSET = "asset"


class MaintenanceWindowKind(StrEnum):
    """A maintenance window's own nature."""

    STANDARD = "standard"
    EMERGENCY = "emergency"
    BLACKOUT = "blackout"


class HolidayScope(StrEnum):
    """What a holiday calendar entry applies to."""

    GLOBAL = "global"
    REGIONAL = "regional"
    ORGANIZATION = "organization"
    CUSTOM = "custom"


class RecoveryAction(StrEnum):
    """What a recovery attempt actually did (docs/054 "FAILURE RECOVERY")."""

    AUTOMATIC_RETRY = "automatic_retry"
    CHECKPOINT_RECOVERY = "checkpoint_recovery"
    RESUME_EXECUTION = "resume_execution"
    RESTART_EXECUTION = "restart_execution"
    ROLLBACK_TRIGGER = "rollback_trigger"
    MANUAL_RECOVERY = "manual_recovery"


class ReportKind(StrEnum):
    """Which report a request wants."""

    EXECUTION = "execution"
    FAILURE = "failure"
    RETRY = "retry"
    PERFORMANCE = "performance"
    QUEUE = "queue"
    CAPACITY = "capacity"
    MAINTENANCE = "maintenance"
    AUDIT = "audit"


class ReportFormat(StrEnum):
    """How a report is rendered."""

    JSON = "json"
    CSV = "csv"
    MARKDOWN = "markdown"


class ReportStatus(StrEnum):
    """A generated report's own build lifecycle."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AuditAction(StrEnum):
    """What an audit row records (docs/054 "AUDIT")."""

    JOB_CREATED = "job_created"
    JOB_UPDATED = "job_updated"
    SCHEDULE_CHANGED = "schedule_changed"
    JOB_PAUSED = "job_paused"
    JOB_RESUMED = "job_resumed"
    JOB_CANCELLED = "job_cancelled"
    JOB_DELETED = "job_deleted"
    JOB_EXECUTED = "job_executed"
    JOB_RETRIED = "job_retried"
    JOB_RECOVERED = "job_recovered"
    MAINTENANCE_WINDOW_CREATED = "maintenance_window_created"
    MAINTENANCE_STARTED = "maintenance_started"
    MAINTENANCE_ENDED = "maintenance_ended"
    REPORT_GENERATED = "report_generated"
    ADMINISTRATIVE = "administrative"


# ---- weightings and derivations ----------------------------------------

PRIORITY_ORDER: Final[dict[JobPriority, int]] = {
    JobPriority.CRITICAL: 0,
    JobPriority.HIGH: 1,
    JobPriority.NORMAL: 2,
    JobPriority.LOW: 3,
    JobPriority.BACKGROUND: 4,
}
"""Lower sorts first, so "more urgent" is always "numerically smaller"
without an off-by-one anyone has to remember."""

OPEN_EXECUTION_STATUSES: Final[frozenset[ExecutionStatus]] = frozenset(
    {
        ExecutionStatus.QUEUED,
        ExecutionStatus.RUNNING,
        ExecutionStatus.PAUSED,
        ExecutionStatus.WAITING,
        ExecutionStatus.BLOCKED,
    }
)
"""Statuses that count as "still in flight" for dashboards and load. A
completed, failed, cancelled, timed-out, skipped, or recovered run is
done, even though not every one of those is a success."""

TERMINAL_EXECUTION_STATUSES: Final[frozenset[ExecutionStatus]] = frozenset(
    {
        ExecutionStatus.COMPLETED,
        ExecutionStatus.FAILED,
        ExecutionStatus.CANCELLED,
        ExecutionStatus.TIMED_OUT,
        ExecutionStatus.SKIPPED,
        ExecutionStatus.RECOVERED,
    }
)

FAILED_EXECUTION_STATUSES: Final[frozenset[ExecutionStatus]] = frozenset(
    {ExecutionStatus.FAILED, ExecutionStatus.TIMED_OUT}
)
"""The statuses a retry sweep treats as worth retrying. ``CANCELLED`` and
``SKIPPED`` were not failures of the work itself and are deliberately
excluded -- retrying a run nobody wanted executed in the first place
would silently override the cancellation."""


def priority_at_least(candidate: JobPriority, floor: JobPriority) -> bool:
    """Whether *candidate* is at least as urgent as *floor*."""
    return PRIORITY_ORDER[candidate] <= PRIORITY_ORDER[floor]


# ---- normalisers ---------------------------------------------------------


def job_type_of(value: str | JobType) -> JobType:
    """Coerce a stored value to :class:`JobType`."""
    return value if isinstance(value, JobType) else JobType(value)


def schedule_type_of(value: str | ScheduleType) -> ScheduleType:
    """Coerce a stored value to :class:`ScheduleType`."""
    return value if isinstance(value, ScheduleType) else ScheduleType(value)


def scheduled_job_status_of(value: str | ScheduledJobStatus) -> ScheduledJobStatus:
    """Coerce a stored value to :class:`ScheduledJobStatus`."""
    return value if isinstance(value, ScheduledJobStatus) else ScheduledJobStatus(value)


def execution_status_of(value: str | ExecutionStatus) -> ExecutionStatus:
    """Coerce a stored value to :class:`ExecutionStatus`."""
    return value if isinstance(value, ExecutionStatus) else ExecutionStatus(value)


def job_priority_of(value: str | JobPriority) -> JobPriority:
    """Coerce a stored value to :class:`JobPriority`."""
    return value if isinstance(value, JobPriority) else JobPriority(value)


def retry_type_of(value: str | RetryType) -> RetryType:
    """Coerce a stored value to :class:`RetryType`."""
    return value if isinstance(value, RetryType) else RetryType(value)


def dependency_type_of(value: str | DependencyType) -> DependencyType:
    """Coerce a stored value to :class:`DependencyType`."""
    return value if isinstance(value, DependencyType) else DependencyType(value)


def dependency_condition_of(value: str | DependencyCondition) -> DependencyCondition:
    """Coerce a stored value to :class:`DependencyCondition`."""
    return value if isinstance(value, DependencyCondition) else DependencyCondition(value)


def calendar_rule_kind_of(value: str | CalendarRuleKind) -> CalendarRuleKind:
    """Coerce a stored value to :class:`CalendarRuleKind`."""
    return value if isinstance(value, CalendarRuleKind) else CalendarRuleKind(value)


def maintenance_window_scope_of(value: str | MaintenanceWindowScope) -> MaintenanceWindowScope:
    """Coerce a stored value to :class:`MaintenanceWindowScope`."""
    return value if isinstance(value, MaintenanceWindowScope) else MaintenanceWindowScope(value)


def maintenance_window_kind_of(value: str | MaintenanceWindowKind) -> MaintenanceWindowKind:
    """Coerce a stored value to :class:`MaintenanceWindowKind`."""
    return value if isinstance(value, MaintenanceWindowKind) else MaintenanceWindowKind(value)


def holiday_scope_of(value: str | HolidayScope) -> HolidayScope:
    """Coerce a stored value to :class:`HolidayScope`."""
    return value if isinstance(value, HolidayScope) else HolidayScope(value)


def recovery_action_of(value: str | RecoveryAction) -> RecoveryAction:
    """Coerce a stored value to :class:`RecoveryAction`."""
    return value if isinstance(value, RecoveryAction) else RecoveryAction(value)


def report_kind_of(value: str | ReportKind) -> ReportKind:
    """Coerce a stored value to :class:`ReportKind`."""
    return value if isinstance(value, ReportKind) else ReportKind(value)


def report_format_of(value: str | ReportFormat) -> ReportFormat:
    """Coerce a stored value to :class:`ReportFormat`."""
    return value if isinstance(value, ReportFormat) else ReportFormat(value)


def report_status_of(value: str | ReportStatus) -> ReportStatus:
    """Coerce a stored value to :class:`ReportStatus`."""
    return value if isinstance(value, ReportStatus) else ReportStatus(value)


__all__ = [
    "FAILED_EXECUTION_STATUSES",
    "OPEN_EXECUTION_STATUSES",
    "PRIORITY_ORDER",
    "TERMINAL_EXECUTION_STATUSES",
    "AuditAction",
    "CalendarRuleKind",
    "DependencyCondition",
    "DependencyType",
    "ExecutionStatus",
    "HolidayScope",
    "JobPriority",
    "JobType",
    "MaintenanceWindowKind",
    "MaintenanceWindowScope",
    "RecoveryAction",
    "ReportFormat",
    "ReportKind",
    "ReportStatus",
    "RetryType",
    "ScheduleType",
    "ScheduledJobStatus",
    "calendar_rule_kind_of",
    "dependency_condition_of",
    "dependency_type_of",
    "execution_status_of",
    "holiday_scope_of",
    "job_priority_of",
    "job_type_of",
    "maintenance_window_kind_of",
    "maintenance_window_scope_of",
    "priority_at_least",
    "recovery_action_of",
    "report_format_of",
    "report_kind_of",
    "report_status_of",
    "retry_type_of",
    "schedule_type_of",
    "scheduled_job_status_of",
]
