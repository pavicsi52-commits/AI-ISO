"""Enumerations for the Reporting Service, per docs/047.

**Reuse note**: ``shared_core.enums`` already owns the platform-wide
vocabularies this service consumes rather than redefines --
``NotificationChannel`` and ``NotificationType`` for delivery,
``Severity`` where a finding needs ranking. Only concepts genuinely
specific to reporting are defined here.

Every enum is a :class:`~enum.StrEnum` so it round-trips through the
``String`` columns this platform uses. **That also means a value loaded
back from Postgres is a plain ``str``, not an enum member** -- compare
with ``==``, never ``is``. See this service's README; the same mistake
shipped three dead features elsewhere in AI-IOS before it was caught.
"""

from __future__ import annotations

from enum import StrEnum


class ReportCategory(StrEnum):
    """Per docs/047 "REPORT CATEGORIES"."""

    INFRASTRUCTURE = "infrastructure"
    INVENTORY = "inventory"
    DISCOVERY = "discovery"
    CONFIGURATION = "configuration"
    AUTOMATION = "automation"
    WORKFLOW = "workflow"
    VALIDATION = "validation"
    MONITORING = "monitoring"
    ALERTING = "alerting"
    COMPLIANCE = "compliance"
    SECURITY = "security"
    INCIDENT = "incident"
    CAPACITY = "capacity"
    AVAILABILITY = "availability"
    PERFORMANCE = "performance"
    EXECUTIVE = "executive"
    OPERATIONAL = "operational"
    FINANCIAL = "financial"
    CUSTOM = "custom"


class ReportType(StrEnum):
    """Per docs/047 "REPORT TYPES"."""

    TABULAR = "tabular"
    SUMMARY = "summary"
    EXECUTIVE = "executive"
    TREND = "trend"
    HISTORICAL = "historical"
    COMPARISON = "comparison"
    COMPLIANCE = "compliance"
    ANALYTICAL = "analytical"
    DASHBOARD_EXPORT = "dashboard_export"
    AI_SUMMARY = "ai_summary"
    CUSTOM = "custom"


class ExportFormat(StrEnum):
    """Per docs/047 "EXPORT FORMATS"."""

    PDF = "pdf"
    XLSX = "xlsx"
    CSV = "csv"
    JSON = "json"
    MARKDOWN = "markdown"
    HTML = "html"
    XML = "xml"


class DataSource(StrEnum):
    """Per docs/047 "DATA SOURCES".

    ``CUSTOM_API`` covers the doc's own "Custom APIs" line: a
    caller-supplied absolute URL, fetched with the caller's own token
    like every other source.
    """

    INVENTORY = "inventory"
    DISCOVERY = "discovery"
    CONFIGURATION = "configuration"
    AUTOMATION = "automation"
    WORKFLOW = "workflow"
    VALIDATION = "validation"
    MONITORING = "monitoring"
    ALERTING = "alerting"
    AI_ASSISTANT = "ai_assistant"
    COMPLIANCE = "compliance"
    INCIDENT = "incident"
    ADMINISTRATION = "administration"
    CUSTOM_API = "custom_api"


class ReportExecutionStatus(StrEnum):
    """Lifecycle of one report generation run."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScheduleFrequency(StrEnum):
    """Per docs/047 "SCHEDULING"."""

    ONE_TIME = "one_time"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CRON = "cron"


class DistributionChannel(StrEnum):
    """Per docs/047 "DISTRIBUTION"."""

    DOWNLOAD = "download"
    EMAIL = "email"
    WEBHOOK = "webhook"
    SHARED_LINK = "shared_link"
    API = "api"
    OBJECT_STORAGE = "object_storage"


class DistributionStatus(StrEnum):
    """Outcome of one delivery attempt."""

    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    EXPIRED = "expired"


class TemplateStatus(StrEnum):
    """Approval state of a report template version.

    Mirrors ``services/ai-assistant-service``'s prompt versioning for
    the same reason: a template is executable content, and running an
    unreviewed one against production data is exactly what the gate
    exists to prevent.
    """

    DRAFT = "draft"
    APPROVED = "approved"
    ARCHIVED = "archived"


class SectionKind(StrEnum):
    """What one designer section renders ("REPORT DESIGNER")."""

    HEADING = "heading"
    TEXT = "text"
    TABLE = "table"
    CHART = "chart"
    METRIC = "metric"
    AI_SUMMARY = "ai_summary"
    PAGE_BREAK = "page_break"


class ChartKind(StrEnum):
    """Chart types the renderer can draw."""

    BAR = "bar"
    LINE = "line"
    PIE = "pie"


class ParameterKind(StrEnum):
    """Type of a declared report parameter ("PARAMETERS")."""

    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    UUID = "uuid"
    ENUM = "enum"


class FilterOperator(StrEnum):
    """Comparison used by one filter clause ("FILTERING")."""

    EQUALS = "eq"
    NOT_EQUALS = "ne"
    GREATER_THAN = "gt"
    GREATER_OR_EQUAL = "gte"
    LESS_THAN = "lt"
    LESS_OR_EQUAL = "lte"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    BETWEEN = "between"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


class ArchiveStatus(StrEnum):
    """State of an archived report artifact ("ARCHIVE")."""

    ACTIVE = "active"
    RESTORED = "restored"
    PURGED = "purged"


class AuditAction(StrEnum):
    """Per docs/047 "AUDIT"."""

    TEMPLATE_CREATED = "template.created"
    TEMPLATE_UPDATED = "template.updated"
    TEMPLATE_APPROVED = "template.approved"
    TEMPLATE_DELETED = "template.deleted"
    REPORT_CREATED = "report.created"
    REPORT_UPDATED = "report.updated"
    REPORT_DELETED = "report.deleted"
    REPORT_GENERATED = "report.generated"
    REPORT_EXPORTED = "report.exported"
    REPORT_DOWNLOADED = "report.downloaded"
    REPORT_DISTRIBUTED = "report.distributed"
    SCHEDULE_CREATED = "schedule.created"
    SCHEDULE_UPDATED = "schedule.updated"
    SCHEDULE_DELETED = "schedule.deleted"
    ARCHIVE_RESTORED = "archive.restored"
    ARCHIVE_PURGED = "archive.purged"


class AuditOutcome(StrEnum):
    """Whether an audited action succeeded."""

    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"


__all__ = [
    "ArchiveStatus",
    "AuditAction",
    "AuditOutcome",
    "ChartKind",
    "DataSource",
    "DistributionChannel",
    "DistributionStatus",
    "ExportFormat",
    "FilterOperator",
    "ParameterKind",
    "ReportCategory",
    "ReportExecutionStatus",
    "ReportType",
    "ScheduleFrequency",
    "SectionKind",
    "TemplateStatus",
]
