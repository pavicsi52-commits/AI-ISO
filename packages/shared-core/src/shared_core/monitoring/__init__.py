"""Enterprise Monitoring Framework.

Observability backbone for AI-IOS
(docs/023_Enterprise_Monitoring_Framework.md.txt "OBJECTIVE"): Health
Checks, Application Monitoring, Resource Monitoring, Dependency
Monitoring, Service Registry Health, Heartbeat, Availability Tracking,
SLA Monitoring, Alerting, Monitoring Metrics, Dashboards. Builds on top
of, and deliberately does not duplicate, the database
(:mod:`shared_core.database`), cache (:mod:`shared_core.cache`), and
queue (:mod:`shared_core.queue`) frameworks' own health/metrics.
"""

from shared_core.monitoring.alerts import Alert, AlertCategory, AlertDispatcher, AlertSink
from shared_core.monitoring.application import (
    ApplicationSnapshot,
    ApplicationStatistics,
    GarbageCollectionStats,
    capture_application_snapshot,
    measure_event_loop_delay,
)
from shared_core.monitoring.availability import AvailabilityTracker, AvailabilityWindow
from shared_core.monitoring.checks import (
    DependencyCheckResult,
    check_http_reachable,
    check_postgresql,
    check_rabbitmq,
    check_redis,
    check_tcp_reachable,
)
from shared_core.monitoring.collector import MonitoringCollector
from shared_core.monitoring.dashboard import build_dashboard_payload
from shared_core.monitoring.decorators import monitored, track_errors
from shared_core.monitoring.dependencies import DependencyMonitor, DependencyMonitorCheckFn
from shared_core.monitoring.exceptions import (
    AlertDispatchError,
    DependencyUnavailableError,
    HealthCheckFailedError,
    RegistrationError,
    ThresholdEvaluationError,
)
from shared_core.monitoring.factory import create_monitoring_framework
from shared_core.monitoring.health import (
    CachedHealthCheck,
    DeepHealthChecker,
    DependencyCheckFn,
    HealthChecker,
    StartupGate,
    liveness,
)
from shared_core.monitoring.heartbeat import Heartbeat, build_heartbeat
from shared_core.monitoring.helpers import bytes_to_human_readable
from shared_core.monitoring.manager import MonitoringManager
from shared_core.monitoring.metrics import (
    ai_request_duration_seconds,
    automation_duration_seconds,
    connector_count,
    database_connections_in_use,
    plugin_count,
    storage_usage_bytes,
    validation_duration_seconds,
    workflow_duration_seconds,
)
from shared_core.monitoring.middleware import ApplicationMonitoringMiddleware
from shared_core.monitoring.registry import MonitoringRegistry
from shared_core.monitoring.resources import (
    DiskUsage,
    NetworkUsage,
    ResourceSnapshot,
    capture_resource_snapshot,
)
from shared_core.monitoring.services import ServiceHealth, ServiceRegistry
from shared_core.monitoring.sla import (
    ServiceLevelIndicators,
    ServiceLevelObjective,
    SlaReport,
    build_sla_report,
)
from shared_core.monitoring.status import calculate_status
from shared_core.monitoring.thresholds import (
    Threshold,
    ThresholdLevel,
    default_cpu_threshold,
    default_disk_threshold,
    default_memory_threshold,
)

__all__ = [
    "Alert",
    "AlertCategory",
    "AlertDispatchError",
    "AlertDispatcher",
    "AlertSink",
    "ApplicationMonitoringMiddleware",
    "ApplicationSnapshot",
    "ApplicationStatistics",
    "AvailabilityTracker",
    "AvailabilityWindow",
    "CachedHealthCheck",
    "DeepHealthChecker",
    "DependencyCheckFn",
    "DependencyCheckResult",
    "DependencyMonitor",
    "DependencyMonitorCheckFn",
    "DependencyUnavailableError",
    "DiskUsage",
    "GarbageCollectionStats",
    "HealthCheckFailedError",
    "HealthChecker",
    "Heartbeat",
    "MonitoringCollector",
    "MonitoringManager",
    "MonitoringRegistry",
    "NetworkUsage",
    "RegistrationError",
    "ResourceSnapshot",
    "ServiceHealth",
    "ServiceLevelIndicators",
    "ServiceLevelObjective",
    "ServiceRegistry",
    "SlaReport",
    "StartupGate",
    "Threshold",
    "ThresholdEvaluationError",
    "ThresholdLevel",
    "ai_request_duration_seconds",
    "automation_duration_seconds",
    "build_dashboard_payload",
    "build_heartbeat",
    "build_sla_report",
    "bytes_to_human_readable",
    "calculate_status",
    "capture_application_snapshot",
    "capture_resource_snapshot",
    "check_http_reachable",
    "check_postgresql",
    "check_rabbitmq",
    "check_redis",
    "check_tcp_reachable",
    "connector_count",
    "create_monitoring_framework",
    "database_connections_in_use",
    "default_cpu_threshold",
    "default_disk_threshold",
    "default_memory_threshold",
    "liveness",
    "measure_event_loop_delay",
    "monitored",
    "plugin_count",
    "storage_usage_bytes",
    "track_errors",
    "validation_duration_seconds",
    "workflow_duration_seconds",
]
