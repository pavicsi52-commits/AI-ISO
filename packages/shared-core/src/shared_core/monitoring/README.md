# Enterprise Monitoring Framework

The observability backbone for AI-IOS
(docs/023_Enterprise_Monitoring_Framework.md.txt "OBJECTIVE"): Health
Checks, Application Monitoring, Resource Monitoring, Dependency
Monitoring, Service Registry Health, Heartbeat, Availability Tracking,
SLA Monitoring, Alert Integration, Monitoring Registry, Monitoring
Metrics, Dashboard Support.

`docs/022_Enterprise_Storage_Framework.md.txt` was skipped -- its body
is a near-duplicate of this document's Monitoring Framework spec (a
doc-authoring error, not a real Storage Framework), confirmed with the
user before proceeding straight to this one.

This package builds on top of, and deliberately does not duplicate, the
database (`shared_core.database`), cache (`shared_core.cache`), and
queue (`shared_core.queue`) frameworks' own health/metrics --
`shared_core.monitoring.checks` adapts their existing health functions
rather than reimplementing connectivity checks.

## Developer Guide

```python
from shared_core.monitoring import create_monitoring_framework

manager = await create_monitoring_framework(
    service_name="gateway", version="1.4.0", environment="production",
)
manager.registry.dependencies.register("postgresql", lambda: check_postgresql(engine))
manager.registry.dependencies.register("redis", lambda: check_redis(redis_client))

status = await manager.overall_status()
heartbeat = await manager.heartbeat()
sla = await manager.sla_report()
await manager.stop()
```

`create_monitoring_framework()` is the one call a service's startup
makes: it builds a `MonitoringManager` and, by default, starts its
background collection loop (periodic application/resource snapshots and
dependency checks, cached so a request handler never pays for a live
check).

### Health Checks

```python
from shared_core.monitoring import HealthChecker, DeepHealthChecker, StartupGate, CachedHealthCheck, liveness

checker = HealthChecker()                       # Prompt 012 baseline: Readiness/Dependency
checker.register("database", check_fn)
result = await checker.run_all()

deep = DeepHealthChecker()                       # more thorough than a reachability ping
deep.register("read_write_roundtrip", roundtrip_check_fn)

gate = StartupGate()                             # one-time startup work
gate.complete()

cached = CachedHealthCheck(check=expensive_check, cache_seconds=5.0)  # Periodic Health Checks
await cached.get()

liveness()                                       # trivially HEALTHY -- "is this process alive"
```

### Application and Resource Monitoring

```python
from shared_core.monitoring import (
    ApplicationStatistics, capture_application_snapshot, measure_event_loop_delay,
    capture_resource_snapshot,
)

stats = ApplicationStatistics()
stats.record_request(response_time_ms=42.0)
stats.record_error()

snapshot = capture_application_snapshot()   # this process: CPU/memory/threads/open files/GC
delay = await measure_event_loop_delay()    # scheduling delay, in seconds
host = capture_resource_snapshot()          # the host: CPU/memory/disk/network/process count
```

`ApplicationMonitoringMiddleware` (raw ASGI, matching
`shared_core.middleware.timing.TimingMiddleware`'s shape) and the
`@monitored`/`@track_errors` decorators feed real HTTP traffic and
background-job calls into the same `ApplicationStatistics` tracker.

### Dependency and Service Health

```python
from shared_core.monitoring import DependencyMonitor, ServiceRegistry
from shared_core.monitoring.checks import check_postgresql, check_redis, check_rabbitmq, check_tcp_reachable, check_http_reachable

dependencies = DependencyMonitor()          # infrastructure *this* service depends on
dependencies.register("postgresql", lambda: check_postgresql(engine))
await dependencies.overall_status()

services = ServiceRegistry()                # peer AI-IOS microservices' self-reported health
services.report("worker-pool", status, version="1.0.0")
services.stale_services(max_age_seconds=60.0)  # missed heartbeats
```

Both registries report `HEALTHY` when nothing has been registered yet
(consistent with `HealthChecker`'s own "no registered checks is
healthy" convention) rather than `calculate_status`'s generic
"nothing to report from" `UNKNOWN`.

Three dependencies already have a client wrapper elsewhere in
shared-core (PostgreSQL, Redis, RabbitMQ) -- `checks.py` adapts their
existing health functions. Everything else (Neo4j, MinIO, OpenSearch,
SMTP, AI Providers, External REST APIs) doesn't have a dedicated client
wrapper in this codebase yet, so `check_tcp_reachable`/
`check_http_reachable` cover them generically.

### Heartbeat, Availability, and SLA

```python
from shared_core.monitoring import build_heartbeat, AvailabilityTracker, ServiceLevelObjective, build_sla_report

heartbeat = build_heartbeat(
    service_name="gateway", version="1.0.0", environment="prod",
    status=status, statistics=stats,
)

availability = AvailabilityTracker()
availability.record(status)                 # call this every time status is (re)determined
availability.availability_percentage

report = build_sla_report(objective=ServiceLevelObjective(), statistics=stats, availability=availability)
report.meets_all_targets
```

`AvailabilityTracker` is purely in-process (process-lifetime-scoped
only) -- this framework must not create business/persistence tables, so
Daily/Weekly/Monthly/Quarterly/Yearly bucketed history that survives a
restart is a downstream business concern, not something built here.
Time before the first `record()` call counts toward neither up nor down
time, so a freshly constructed tracker reports `100.0` rather than a
misleading near-zero reading.

### Alerts and Thresholds

```python
from shared_core.monitoring import AlertDispatcher, Alert, AlertCategory, Threshold, ThresholdLevel, default_cpu_threshold

dispatcher = AlertDispatcher()
dispatcher.register_sink(my_notification_sink)   # a future Notification Framework's concern
await dispatcher.trigger(Alert(category=AlertCategory.HIGH_CPU, level=ThresholdLevel.CRITICAL, message="..."))

threshold = default_cpu_threshold()
threshold.evaluate(92.0)   # -> ThresholdLevel.CRITICAL
```

Every triggered alert is audit-logged via `shared_core.logging`
regardless of whether any sink is registered, so nothing is silently
lost even before a real delivery integration exists.

### Registry and Dashboard

```python
from shared_core.monitoring import MonitoringRegistry, build_dashboard_payload

registry = MonitoringRegistry()   # composes health/deep_health/dependencies/services/alerts
registry.register_threshold(default_cpu_threshold())
registry.register_dashboard("grafana-main", "Primary Grafana overview board")

payload = build_dashboard_payload(
    service_name="gateway", status=status, application=snapshot,
    resources=host, dependencies=[], availability=availability.current_window(),
)  # plain, JSON-serializable dict
```

`build_dashboard_payload` is data-shaping only -- Grafana's own need is
already met by this package's registered Prometheus metrics (scraped
externally); nothing extra to run here.

### Metrics

Most of docs/023's "METRICS COLLECTION" list is already covered
elsewhere and deliberately not duplicated: Request Count/Response Time
(`shared_core.metrics.standard`, Prompt 012), Queue Size/Worker Count
(`shared_core.queue.metrics`, Prompt 021), Redis Hit Ratio/Cache Miss
Ratio (`shared_core.cache.statistics.CacheStatistics`, Prompt 019).
`shared_core.monitoring.metrics` adds only genuinely new
instrumentation: `database_connections_in_use`, `storage_usage_bytes`,
`workflow_duration_seconds`, `automation_duration_seconds`,
`validation_duration_seconds`, `ai_request_duration_seconds`,
`plugin_count`, `connector_count`.

## Architecture Notes

- **`HealthStatus` extended from four to six values** (`HEALTHY`,
  `DEGRADED`, `WARNING`, `UNHEALTHY`, `MAINTENANCE`, `UNKNOWN`).
  `UNHEALTHY` was kept rather than renamed to the spec's "Unavailable"
  term -- 14 existing call sites across `database`/`cache`/`events`/
  `queue`/`monitoring` made that rename too disruptive; `WARNING`/
  `MAINTENANCE` are additive.
- **No circular imports**: `monitoring -> database`/`cache`/`queue` (as
  read-only health adapters in `checks.py`) is safe and one-directional
  -- none of those packages depend on `monitoring`.
- **`DependencyCheckFn` naming collision, resolved by scoping**: the
  Prompt 012 baseline `health.py` already defined `DependencyCheckFn =
  Callable[[], Awaitable[HealthStatus]]`; the new `dependencies.py`
  needed a different signature (`Awaitable[DependencyCheckResult]`) for
  the same concept at a different layer, so it's named
  `DependencyMonitorCheckFn` instead of colliding.
- **`DependencyMonitor`/`ServiceRegistry` empty-registry status fixed to
  `HEALTHY`, not `calculate_status`'s generic `UNKNOWN`** -- found while
  writing tests: a freshly constructed registry with nothing registered
  yet is a normal starting state, not an unknown one, and the Prompt-012
  baseline `HealthChecker` already established "no registered checks is
  healthy" as this framework's convention.
- **`AvailabilityTracker.current_window()` fixed to measure from the
  first known status, not from tracker construction** -- found while
  writing tests: `total_seconds` used to be wall-clock time since the
  tracker object was created, while `up_seconds`/`down_seconds` only
  started accumulating after the first `record()` call, so querying
  availability before (or immediately after) that first call reported a
  misleading near-zero percentage instead of the `100.0` the class's own
  docstring promised.
- **`checks.py`'s framework adapters import `database`/`cache`/`queue`
  health functions at module level**, not lazily inside each function --
  none of those three packages are optional extras in this monorepo, so
  there's no real deferred-import benefit, and doing so avoids a
  PLC0415 lint exception.
