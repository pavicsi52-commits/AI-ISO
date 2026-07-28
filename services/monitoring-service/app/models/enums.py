"""Enumerations for the monitoring service.

Every enum member is verbatim from docs/044's own named lists except
where noted -- each such deviation is explained inline rather than
silently invented. Two concepts are deliberately *not* redefined here:
overall health status reuses
:class:`shared_core.enums.health_status.HealthStatus` directly (six
values: healthy/degraded/warning/unhealthy/maintenance/unknown,
already the platform-wide "worst-case status rollup" vocabulary every
service's own ``/readiness`` endpoint uses via
:func:`shared_core.monitoring.status.calculate_status`), and threshold
breach severity reuses
:class:`shared_core.monitoring.thresholds.ThresholdLevel` directly
(five values: informational/low/medium/high/critical) -- introducing a
second, parallel enum for either concept would contradict the exact
"reuse the framework, don't reinvent" precedent
``shared_core.monitoring.status``'s own module docstring already
established.
"""

from __future__ import annotations

from enum import StrEnum


class MonitoringTargetType(StrEnum):
    """Per docs/044's own "MONITORING TARGETS" list (14 values,
    singularized from the doc's own plural section headings -- "Target
    Groups"/"Dynamic Inventory" from the same list are capabilities,
    not target types).
    """

    PHYSICAL_SERVER = "physical_server"
    VIRTUAL_MACHINE = "virtual_machine"
    CONTAINER = "container"
    KUBERNETES = "kubernetes"
    APPLICATION = "application"
    MICROSERVICE = "microservice"
    DATABASE = "database"
    STORAGE = "storage"
    NETWORK_DEVICE = "network_device"
    CLOUD_RESOURCE = "cloud_resource"
    INDUSTRIAL_CONTROLLER = "industrial_controller"
    EDGE_DEVICE = "edge_device"
    IOT_DEVICE = "iot_device"
    CUSTOM_TARGET = "custom_target"


class MetricType(StrEnum):
    """Per docs/044's own "METRIC COLLECTION" list (18 values, verbatim)."""

    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"
    DISK_USAGE = "disk_usage"
    FILESYSTEM = "filesystem"
    IOPS = "iops"
    LATENCY = "latency"
    BANDWIDTH = "bandwidth"
    PACKET_LOSS = "packet_loss"
    PROCESS_STATUS = "process_status"
    SERVICE_STATUS = "service_status"
    APPLICATION_METRICS = "application_metrics"
    DATABASE_METRICS = "database_metrics"
    NETWORK_METRICS = "network_metrics"
    POWER_METRICS = "power_metrics"
    TEMPERATURE = "temperature"
    FAN_SPEED = "fan_speed"
    REDFISH_METRICS = "redfish_metrics"
    CUSTOM_METRICS = "custom_metrics"


class HealthCheckType(StrEnum):
    """Per docs/044's own "HEALTH MONITORING" "Support" list (7 values --
    "Overall Health Score" from the same list is a computed value, not
    a check type of its own).
    """

    HEARTBEAT = "heartbeat"
    SERVICE_AVAILABILITY = "service_availability"
    APPLICATION_HEALTH = "application_health"
    INFRASTRUCTURE_HEALTH = "infrastructure_health"
    DEPENDENCY_HEALTH = "dependency_health"
    COMPONENT_HEALTH = "component_health"
    CLUSTER_HEALTH = "cluster_health"


class AvailabilityStatus(StrEnum):
    """Not its own named list in docs/044, but required by "AVAILABILITY"
    "Track"'s own "Uptime"/"Downtime"/"Maintenance Windows"/"Outages"
    entries -- added directly via design reasoning, the same "required
    concept, no literal enum list" precedent every prior AI-IOS service
    has established at least once. Backs ``MonitoringAvailability.status``.
    """

    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"
    MAINTENANCE = "maintenance"


class ThresholdType(StrEnum):
    """Per docs/044's own "THRESHOLDS" "Support" list (7 values, verbatim).

    Orthogonal to breach severity (``shared_core.monitoring.thresholds
    .ThresholdLevel``, reused directly rather than redefined here) --
    this classifies *how* a threshold's own limits are computed
    (a fixed number vs. a rolling baseline vs. an adaptive model), not
    *how bad* a breach of it is.
    """

    STATIC = "static"
    DYNAMIC = "dynamic"
    BASELINE = "baseline"
    ADAPTIVE = "adaptive"
    PERCENTAGE = "percentage"
    TIME_BASED = "time_based"
    CUSTOM = "custom"


class MonitoringRuleType(StrEnum):
    """Per docs/044's own "RULE ENGINE" "Support" list -- five entries
    that name a genuine rule *kind* (``Metric Rules``, ``Composite
    Rules``, ``Dependency Rules``, ``Rate-of-Change Rules``,
    ``Correlation Rules``). The remaining three entries from the same
    list (``Anomaly Hooks``, ``Window Aggregation``, ``Escalation
    Triggers``) are capabilities every rule may configure
    (``MonitoringRule.window_seconds``/``escalation_after_seconds``),
    not rule types of their own.
    """

    METRIC = "metric"
    COMPOSITE = "composite"
    DEPENDENCY = "dependency"
    RATE_OF_CHANGE = "rate_of_change"
    CORRELATION = "correlation"


class AggregationFunction(StrEnum):
    """Not its own named list in docs/044, but required by "TIME SERIES"
    "Support"'s own "Aggregation"/"Downsampling" entries -- added
    directly via design reasoning. Backs both
    ``MonitoringRetention``'s own downsampling configuration and ad hoc
    historical-query aggregation.
    """

    AVG = "avg"
    SUM = "sum"
    MIN = "min"
    MAX = "max"
    COUNT = "count"
    P95 = "p95"
    P99 = "p99"


class SyntheticCheckType(StrEnum):
    """Per docs/044's own "SYNTHETIC MONITORING" "Support" list (7
    values -- "Scheduled Tests" from the same list is a scheduling
    capability every synthetic test already has via its own
    ``schedule``, not a check type of its own). ``TCP``/``DNS`` reuse
    the exact collector shape
    ``services/validation-service/app/collectors/network.py`` already
    established (real asyncio-socket checks, no remote execution
    capability needed); ``HTTP``/``API``/``SSH``/``DATABASE`` are new
    collectors following that same signature/error convention.
    """

    HTTP = "http"
    TCP = "tcp"
    DNS = "dns"
    API = "api"
    SSH = "ssh"
    DATABASE = "database"
    CUSTOM_SCRIPT = "custom_script"


class DependencyType(StrEnum):
    """Per docs/044's own "DEPENDENCY HEALTH" "Support" list -- three
    entries that name a genuine dependency *kind* (``Service
    Dependency``, ``Application Dependency``, ``Infrastructure
    Dependency``). The remaining entries from the same list
    ("Topology-aware Health", "Parent/Child Health", "Blast Radius
    Calculation") are capabilities the dependency graph enables, not
    dependency types of their own.
    """

    SERVICE = "service"
    APPLICATION = "application"
    INFRASTRUCTURE = "infrastructure"


class SLAType(StrEnum):
    """Per docs/044's own "SLA / SLO" "Track" list's own "Availability
    SLA"/"Performance SLA" entries (2 values).
    """

    AVAILABILITY = "availability"
    PERFORMANCE = "performance"


class SLOType(StrEnum):
    """Docs/044's own "SLA / SLO" "Track" list names only one literal
    example ("Latency SLO"); a real, useful SLO taxonomy needs more
    than a single type to track, so this is extended via design
    reasoning to the other objective categories the same section's own
    "Error Budget"/"Objective Violations" language implies exist.
    """

    LATENCY = "latency"
    AVAILABILITY = "availability"
    ERROR_RATE = "error_rate"
    THROUGHPUT = "throughput"
    CUSTOM = "custom"


class ComplianceStatus(StrEnum):
    """Not its own named list in docs/044, but required by "SLA / SLO"
    "Track"'s own "Objective Violations"/"Compliance Percentage"
    entries -- added directly via design reasoning. Backs both
    ``MonitoringSLA.status`` and ``MonitoringSLO.status``.
    """

    COMPLIANT = "compliant"
    AT_RISK = "at_risk"
    VIOLATED = "violated"


class MonitoringReportType(StrEnum):
    """Per docs/044's own "REPORTING" "Generate" list (8 values, verbatim)."""

    HEALTH = "health"
    AVAILABILITY = "availability"
    PERFORMANCE = "performance"
    CAPACITY = "capacity"
    EXECUTIVE = "executive"
    SLA = "sla"
    SLO = "slo"
    HISTORICAL = "historical"


class AuditOutcome(StrEnum):
    """Reused ``SUCCESS``/``FAILURE`` shape, the same convention every
    prior AI-IOS audit-trail table established.
    """

    SUCCESS = "success"
    FAILURE = "failure"


__all__ = [
    "AggregationFunction",
    "AuditOutcome",
    "AvailabilityStatus",
    "ComplianceStatus",
    "DependencyType",
    "HealthCheckType",
    "MetricType",
    "MonitoringReportType",
    "MonitoringRuleType",
    "MonitoringTargetType",
    "SLAType",
    "SLOType",
    "SyntheticCheckType",
    "ThresholdType",
]
