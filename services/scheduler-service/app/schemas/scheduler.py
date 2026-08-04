"""Request and response schemas for the scheduler API surface."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import (
    AuditAction,
    CalendarRuleKind,
    DependencyCondition,
    DependencyType,
    ExecutionStatus,
    HolidayScope,
    JobPriority,
    JobType,
    MaintenanceWindowKind,
    MaintenanceWindowScope,
    RecoveryAction,
    ReportFormat,
    ReportKind,
    ReportStatus,
    RetryType,
    ScheduledJobStatus,
)

# ---- jobs -------------------------------------------------------------------


class JobCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    job_type: JobType
    description: str | None = Field(default=None, max_length=4_000)
    priority: JobPriority = JobPriority.NORMAL
    owner_id: str | None = Field(default=None, max_length=255)
    timezone: str = "UTC"
    payload: dict[str, Any] = Field(default_factory=dict)
    job_metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    timeout_seconds: float | None = Field(default=None, gt=0)


class JobUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    priority: JobPriority | None = None
    owner_id: str | None = None
    timezone: str | None = None
    payload: dict[str, Any] | None = None
    job_metadata: dict[str, Any] | None = None
    tags: list[str] | None = None
    timeout_seconds: float | None = Field(default=None, gt=0)


class JobResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    job_type: JobType
    status: ScheduledJobStatus
    priority: JobPriority
    description: str | None
    owner_id: str | None
    timezone: str
    payload: dict[str, Any]
    job_metadata: dict[str, Any]
    tags: list[str]
    timeout_seconds: float | None
    last_run_at: datetime | None
    next_run_at: datetime | None
    paused_at: datetime | None
    disabled_at: datetime | None
    run_count: int
    failure_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1_000)


class JobHistoryResponse(BaseModel):
    id: UUID
    job_id: UUID
    from_status: str | None
    to_status: str
    occurred_at: datetime
    actor_id: str | None
    note: str | None

    model_config = {"from_attributes": True}


# ---- triggers -----------------------------------------------------------------


class TriggerCreateRequest(BaseModel):
    trigger_type: str = Field(min_length=1, max_length=32)
    cron_expression: str | None = None
    run_at: datetime | None = None
    interval_seconds: float | None = Field(default=None, gt=0)
    calendar_rule: CalendarRuleKind | None = None
    calendar_config: dict[str, Any] = Field(default_factory=dict)
    event_name: str | None = None
    description: str | None = None
    enabled: bool = True


class TriggerEnabledRequest(BaseModel):
    enabled: bool


class TriggerResponse(BaseModel):
    id: UUID
    job_id: UUID
    trigger_type: str
    enabled: bool
    cron_expression: str | None
    run_at: datetime | None
    interval_seconds: float | None
    calendar_rule: CalendarRuleKind | None
    calendar_config: dict[str, Any]
    event_name: str | None
    description: str | None

    model_config = {"from_attributes": True}


class JobScheduleResponse(BaseModel):
    job_id: UUID
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_evaluated_at: datetime | None
    is_paused: bool
    pause_reason: str | None

    model_config = {"from_attributes": True}


# ---- dependencies -----------------------------------------------------------


class DependencyCreateRequest(BaseModel):
    parent_job_id: UUID
    dependency_type: DependencyType = DependencyType.SEQUENTIAL
    condition: DependencyCondition | None = None


class DependencyResponse(BaseModel):
    id: UUID
    parent_job_id: UUID
    child_job_id: UUID
    dependency_type: DependencyType
    condition: DependencyCondition | None

    model_config = {"from_attributes": True}


# ---- retry policy -------------------------------------------------------------


class RetryPolicySetRequest(BaseModel):
    retry_type: RetryType = RetryType.EXPONENTIAL_BACKOFF
    max_attempts: int = Field(default=3, ge=1, le=100)
    base_delay_seconds: float = Field(default=5.0, gt=0)
    max_delay_seconds: float = Field(default=300.0, gt=0)
    retry_conditions: dict[str, Any] = Field(default_factory=dict)
    dead_letter_enabled: bool = True


class RetryPolicyResponse(BaseModel):
    id: UUID
    job_id: UUID
    retry_type: RetryType
    max_attempts: int
    base_delay_seconds: float
    max_delay_seconds: float
    retry_conditions: dict[str, Any]
    dead_letter_enabled: bool

    model_config = {"from_attributes": True}


# ---- priorities ---------------------------------------------------------------


class PriorityPolicySetRequest(BaseModel):
    label: str = Field(min_length=1, max_length=128)
    color: str | None = None
    escalate_after_minutes: int | None = Field(default=None, ge=1, le=1_440)
    escalate_to: JobPriority | None = None


class PriorityPolicyResponse(BaseModel):
    id: UUID
    priority: JobPriority
    label: str
    color: str | None
    escalate_after_minutes: int | None
    escalate_to: JobPriority | None

    model_config = {"from_attributes": True}


# ---- executions ---------------------------------------------------------------


class JobExecutionResponse(BaseModel):
    id: UUID
    job_id: UUID
    status: ExecutionStatus
    trigger_source: str
    priority_snapshot: JobPriority
    queued_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: float | None
    worker_id: str | None
    node_id: str | None
    exit_code: int | None
    attempt_number: int
    retries_used: int
    error: str | None

    model_config = {"from_attributes": True}


class JobRunResponse(BaseModel):
    execution: JobExecutionResponse


class ExecutionLogResponse(BaseModel):
    id: UUID
    execution_id: UUID
    occurred_at: datetime
    level: str
    message: str

    model_config = {"from_attributes": True}


# ---- failures / recovery -------------------------------------------------------


class FailureResponse(BaseModel):
    id: UUID
    job_id: UUID
    execution_id: UUID
    occurred_at: datetime
    failure_reason: str
    error_detail: str | None
    is_terminal: bool
    retry_at: datetime | None
    retried: bool
    recovery_action: RecoveryAction | None
    recovered: bool
    recovered_at: datetime | None
    recovered_by: str | None

    model_config = {"from_attributes": True}


class RecoverFailureRequest(BaseModel):
    action: RecoveryAction
    recovered_by: str | None = None


# ---- maintenance windows -------------------------------------------------------


class MaintenanceWindowCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    starts_at: datetime
    ends_at: datetime
    scope: MaintenanceWindowScope = MaintenanceWindowScope.ORGANIZATION
    scope_id: str | None = None
    kind: MaintenanceWindowKind = MaintenanceWindowKind.STANDARD
    description: str | None = None
    timezone: str = "UTC"
    recurrence: CalendarRuleKind = CalendarRuleKind.NONE
    recurrence_until: datetime | None = None
    allow_critical_override: bool = False


class MaintenanceWindowResponse(BaseModel):
    id: UUID
    scope: MaintenanceWindowScope
    scope_id: str | None
    kind: MaintenanceWindowKind
    title: str
    description: str | None
    starts_at: datetime
    ends_at: datetime
    timezone: str
    recurrence: CalendarRuleKind
    recurrence_until: datetime | None
    allow_critical_override: bool

    model_config = {"from_attributes": True}


# ---- holidays -------------------------------------------------------------------


class HolidayCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    holiday_date: date
    scope: HolidayScope = HolidayScope.ORGANIZATION
    scope_id: str | None = None
    is_recurring: bool = True
    description: str | None = None


class HolidayResponse(BaseModel):
    id: UUID
    scope: HolidayScope
    scope_id: str | None
    name: str
    description: str | None
    holiday_date: date
    is_recurring: bool

    model_config = {"from_attributes": True}


# ---- statistics / reports / audit ------------------------------------------------


class StatisticsRollupRequest(BaseModel):
    window_start: datetime
    window_end: datetime


class StatisticResponse(BaseModel):
    id: UUID
    window_start: datetime
    window_end: datetime
    jobs_scheduled: int
    jobs_completed: int
    jobs_failed: int
    jobs_cancelled: int
    retry_rate: float
    avg_queue_length: float
    avg_execution_time_seconds: float | None
    average_delay_seconds: float | None
    success_rate: float
    scheduler_availability: float | None
    by_job_type: dict[str, int]
    by_priority: dict[str, int]

    model_config = {"from_attributes": True}


class ReportGenerateRequest(BaseModel):
    kind: ReportKind
    report_format: ReportFormat = ReportFormat.JSON
    title: str | None = None


class ReportResponse(BaseModel):
    id: UUID
    kind: ReportKind
    report_format: ReportFormat
    title: str
    status: ReportStatus
    content: dict[str, Any]
    row_count: int | None
    generated_by: str | None
    generated_at: datetime | None
    duration_ms: float | None
    error: str | None

    model_config = {"from_attributes": True}


class AuditEntryResponse(BaseModel):
    id: UUID
    action: AuditAction
    entity_type: str
    entity_id: UUID | None
    entity_reference: str | None
    actor_id: str | None
    actor_type: str
    occurred_at: datetime
    summary: str
    succeeded: bool
    changes: dict[str, Any]
    context: dict[str, Any]

    model_config = {"from_attributes": True}


__all__ = [
    "AuditEntryResponse",
    "DependencyCreateRequest",
    "DependencyResponse",
    "ExecutionLogResponse",
    "FailureResponse",
    "HolidayCreateRequest",
    "HolidayResponse",
    "JobCancelRequest",
    "JobCreateRequest",
    "JobExecutionResponse",
    "JobHistoryResponse",
    "JobResponse",
    "JobRunResponse",
    "JobScheduleResponse",
    "JobUpdateRequest",
    "MaintenanceWindowCreateRequest",
    "MaintenanceWindowResponse",
    "PriorityPolicyResponse",
    "PriorityPolicySetRequest",
    "RecoverFailureRequest",
    "ReportGenerateRequest",
    "ReportResponse",
    "RetryPolicyResponse",
    "RetryPolicySetRequest",
    "StatisticResponse",
    "StatisticsRollupRequest",
    "TriggerCreateRequest",
    "TriggerEnabledRequest",
    "TriggerResponse",
]
