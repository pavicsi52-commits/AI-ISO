"""Enumerations for the Dashboard Service, per docs/048.

**Reuse note**: ``shared_core.enums`` already owns the platform-wide
vocabularies this service consumes rather than redefines --
``Severity`` for filter thresholds, ``NotificationChannel`` and
``NotificationType`` for delivery.

Every enum is a :class:`~enum.StrEnum` so it round-trips through the
``String`` columns this platform uses. **That also means a value loaded
back from Postgres is a plain ``str``, not an enum member** -- compare
with ``==``, or normalise first; never ``is``. That mistake has now
shipped as a live bug four times across this platform (prompt
templates, alert maintenance windows, automation dispatch, and GitOps
conflict detection), so every comparison in this service goes through
an explicit normaliser.
"""

from __future__ import annotations

from enum import StrEnum


class DashboardType(StrEnum):
    """Per docs/048 "DASHBOARD TYPES"."""

    EXECUTIVE = "executive"
    OPERATIONS = "operations"
    INFRASTRUCTURE = "infrastructure"
    MONITORING = "monitoring"
    VALIDATION = "validation"
    AUTOMATION = "automation"
    WORKFLOW = "workflow"
    ALERT = "alert"
    COMPLIANCE = "compliance"
    SECURITY = "security"
    CAPACITY = "capacity"
    PERFORMANCE = "performance"
    INVENTORY = "inventory"
    AI_INSIGHTS = "ai_insights"
    CUSTOM = "custom"


class WidgetType(StrEnum):
    """Per docs/048 "WIDGET TYPES"."""

    METRIC_CARD = "metric_card"
    GAUGE = "gauge"
    LINE_CHART = "line_chart"
    BAR_CHART = "bar_chart"
    AREA_CHART = "area_chart"
    PIE_CHART = "pie_chart"
    DONUT_CHART = "donut_chart"
    HEATMAP = "heatmap"
    TOPOLOGY_GRAPH = "topology_graph"
    STATUS_MATRIX = "status_matrix"
    TIMELINE = "timeline"
    ALERT_FEED = "alert_feed"
    EVENT_FEED = "event_feed"
    TABLE = "table"
    TREE_VIEW = "tree_view"
    MARKDOWN = "markdown"
    AI_INSIGHT = "ai_insight"
    CUSTOM = "custom"


class DataSource(StrEnum):
    """Per docs/048 "DATA SOURCES".

    ``CUSTOM_API`` covers a caller-supplied absolute URL, fetched with
    the caller's own token like every other source. ``STATIC`` needs no
    fetch at all -- a markdown widget carries its own content.
    """

    INVENTORY = "inventory"
    DISCOVERY = "discovery"
    CONFIGURATION = "configuration"
    AUTOMATION = "automation"
    WORKFLOW = "workflow"
    VALIDATION = "validation"
    MONITORING = "monitoring"
    ALERTING = "alerting"
    REPORTING = "reporting"
    AI_ASSISTANT = "ai_assistant"
    COMPLIANCE = "compliance"
    INCIDENT = "incident"
    ADMINISTRATION = "administration"
    TOPOLOGY = "topology"
    CUSTOM_API = "custom_api"
    STATIC = "static"


class DashboardVisibility(StrEnum):
    """Per docs/048 "SHARING"."""

    PRIVATE = "private"
    ORGANIZATION = "organization"
    PROJECT = "project"
    LINK = "link"


class SharePermission(StrEnum):
    """What a share grants its recipient.

    ``VIEW`` is deliberately the default everywhere: a dashboard shared
    for visibility should not become editable by accident.
    """

    VIEW = "view"
    EDIT = "edit"
    MANAGE = "manage"


class ThemeMode(StrEnum):
    """Per docs/048 "THEMES"."""

    LIGHT = "light"
    DARK = "dark"
    CUSTOM = "custom"


class LayoutBreakpoint(StrEnum):
    """Responsive breakpoints a saved layout can target.

    A layout is stored per breakpoint rather than computed, so a
    dashboard author can place widgets deliberately on a phone instead
    of accepting whatever a reflow algorithm produces.
    """

    MOBILE = "mobile"
    TABLET = "tablet"
    DESKTOP = "desktop"
    WIDE = "wide"


class RefreshMode(StrEnum):
    """How a widget's data is kept current ("REAL-TIME UPDATES")."""

    MANUAL = "manual"
    POLLING = "polling"
    STREAM = "stream"


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


class TopologyQueryKind(StrEnum):
    """Per docs/048 "TOPOLOGY VISUALIZATION"."""

    NEIGHBORS = "neighbors"
    DEPENDENCIES = "dependencies"
    DEPENDENTS = "dependents"
    BLAST_RADIUS = "blast_radius"
    SERVICE_MAP = "service_map"
    CLUSTER_MAP = "cluster_map"
    APPLICATION_TOPOLOGY = "application_topology"


class WidgetStatus(StrEnum):
    """Outcome of resolving one widget's data."""

    OK = "ok"
    EMPTY = "empty"
    FAILED = "failed"
    UNAUTHORIZED = "unauthorized"


class StreamEventKind(StrEnum):
    """Frames a real-time subscriber can receive."""

    SNAPSHOT = "snapshot"
    UPDATE = "update"
    PRESENCE = "presence"
    HEARTBEAT = "heartbeat"
    ERROR = "error"


class AuditAction(StrEnum):
    """Per docs/048 "AUDIT"."""

    DASHBOARD_CREATED = "dashboard.created"
    DASHBOARD_UPDATED = "dashboard.updated"
    DASHBOARD_DELETED = "dashboard.deleted"
    DASHBOARD_VIEWED = "dashboard.viewed"
    WIDGET_ADDED = "widget.added"
    WIDGET_UPDATED = "widget.updated"
    WIDGET_REMOVED = "widget.removed"
    LAYOUT_CHANGED = "layout.changed"
    LAYOUT_RESTORED = "layout.restored"
    DASHBOARD_SHARED = "dashboard.shared"
    SHARE_REVOKED = "share.revoked"
    PERMISSION_CHANGED = "permission.changed"
    THEME_CHANGED = "theme.changed"
    TEMPLATE_CREATED = "template.created"
    TEMPLATE_APPLIED = "template.applied"


class AuditOutcome(StrEnum):
    """Whether an audited action succeeded."""

    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"


__all__ = [
    "AuditAction",
    "AuditOutcome",
    "DashboardType",
    "DashboardVisibility",
    "DataSource",
    "FilterOperator",
    "LayoutBreakpoint",
    "RefreshMode",
    "SharePermission",
    "StreamEventKind",
    "ThemeMode",
    "TopologyQueryKind",
    "WidgetStatus",
    "WidgetType",
]
