# Monitoring Service

Enterprise monitoring and observability service for AI-IOS
([`docs/044_Enterprise_Monitoring_Service.md`](../../docs/044_Enterprise_Monitoring_Service.md)):
continuously collects, stores, processes, correlates, and evaluates
operational telemetry across infrastructure, cloud, Kubernetes,
applications, databases, and industrial systems — distributed
collectors, time-series metrics, health/availability/performance
monitoring, synthetic checks, dependency-aware health, SLA/SLO
tracking, analytics, and reporting. The fifteenth AI-IOS microservice
built on `packages/shared-core`, following
`services/authentication-service`, `services/user-management-service`,
`services/rbac-service`, `services/organization-service`,
`services/project-service`, `services/secrets-management-service`,
`services/inventory-service`, `services/discovery-service`,
`services/asset-management-service`,
`services/configuration-management-service`,
`services/automation-service`, `services/playbook-service`,
`services/workflow-runtime-service`, and `services/validation-service`.

## Architecture

Standard service structure per
[`docs/008_Backend_Master_Architecture.md.txt`](../../docs/008_Backend_Master_Architecture.md.txt),
mostly flat (`app/services/`/`app/repositories/`/`app/models/`/
`app/schemas/`/`app/api/`), with a handful of genuinely distinct
modules:

- `app/collectors/` — the data-gathering layer. Real, native
  collectors (`network.py`: TCP connectivity/port, DNS resolution, TLS
  certificate expiry, HTTP/API checks) run directly from this process;
  delegated collectors (`remote.py`) dispatch a live automation-service
  job for OS-level metrics and `SSH`/`DATABASE`/`CUSTOM_SCRIPT`
  synthetic checks this service has no remote-execution capability of
  its own to perform; read-only collectors (`service_state.py`) read
  already-recorded state from Inventory, Discovery, Configuration
  Management, Workflow Runtime, and Validation; `synthetic.py`
  dispatches a `MonitoringSyntheticTest`'s own `check_type` onto the
  same low-level probing helpers `network.py`/`remote.py` already
  define, rather than duplicating them.
- `app/health/engine.py` — health-status rollup, built entirely on
  `shared_core.monitoring.status.calculate_status` (the platform-wide
  worst-case status vocabulary every service's own `/readiness`
  endpoint already uses) for both per-target multi-check-type rollup
  and dependency-graph "blast radius" rollup.
- `app/rules/thresholds.py` / `app/rules/evaluator.py` — threshold
  breach evaluation reuses `shared_core.monitoring.thresholds
  .Threshold.evaluate()` directly (converting a persisted
  `MonitoringThreshold` row into that dataclass rather than
  duplicating its breach logic); rule condition evaluation reuses
  `shared_core.workflow.expressions.evaluate_condition` (Jinja2
  sandboxed), the same proven-safe evaluator
  `services/validation-service`'s own rule engine already established.
- `app/timeseries/` — aggregation (`AVG`/`SUM`/`MIN`/`MAX`/`COUNT`/
  `P95`/`P99`), downsampling (fixed-width time buckets), and retention
  policy resolution (most-specific-metric-type-wins, falling back to
  an organization default, falling back to a 90-day platform default).
- `app/services/collection.py` — the central "Monitoring Engine"
  orchestrator. Runs a `MonitoringCollector` against one or many
  targets, splitting concurrent I/O collection from always-sequential
  database persistence (see "Real bugs found via testing" below),
  dispatches persisted data to the right table by `collector_key`
  (single numeric metric, named-metrics-dict, or health signal),
  evaluates thresholds/rules, and publishes events.
- `app/services/synthetic_execution.py` — runs one scheduled synthetic
  check and persists its own outcome, reusing `MonitoringMetricSeries`/
  `MonitoringHealth` rather than a dedicated results table.
- `app/scheduling/registrar.py` + `app/workers/collection_worker.py` —
  every active collector/synthetic test is registered with
  `shared_core.scheduler.SchedulerManager` on its own `interval_seconds`
  (`FIXED_RATE` schedule), matching `services/workflow-runtime-service`'s
  own `CRON`/`RECURRING` timer pattern more closely than
  `services/validation-service`'s own on-demand-execute pattern — there
  is no queue-based "run now" worker here, since every collection run
  is either scheduler-triggered or (for a manual test) invoked directly
  through the service layer.

### Design decisions worth knowing

- **Two real database-integrity bugs found and fixed during testing,
  both the same root cause: using an unrelated row's own id as a
  foreign key without verifying a matching row actually exists.**
  1. `MonitoringSyntheticExecutionService.run()` originally passed
     `test.id` directly as `MonitoringMetricSeries.metric_id` — a real
     foreign key into `monitoring_metrics`, and a synthetic test's id
     is never a metric's id. The first "record synthetic latency" test
     hit a genuine `ForeignKeyViolationError`. Fixed by
     `MonitoringMetricService.get_or_create_by_name` lazily resolving
     (and reusing across every later run) one shared
     `"synthetic_latency_ms"` metric per organization — the same
     "reuse the same row across repeated runs" pattern
     `MonitoringTargetService.get_or_create` already established.
  2. The same service also fell back to `test.id` as `target_id` for a
     *target-less* synthetic test (one probing a bare external
     endpoint, per `MonitoringSyntheticTest`'s own docstring) —
     `MonitoringHealth.target_id` is a real, non-nullable foreign key
     into `monitoring_targets`, so this raised the identical class of
     error the moment a target-less test's first failure was recorded.
     Fixed by `MonitoringTargetService.get_or_create` registering (and
     reusing) one lightweight `CUSTOM_TARGET` row representing the
     test itself, resolved once at the top of `run()` via a new
     `_resolve_target_id` helper.
- **`_persist_health_signal`'s own breach detection was too narrow —
  found via the collection-orchestrator test suite.** The first
  version only checked `unresolved_drift_count`/`non_compliant_count`/
  `failed_count` (the three service-state collectors' own field
  names), so a failed `dns` collection (`{"resolved": false}`) — also
  routed through this same "no numeric value to persist as a metric"
  bucket — was silently recorded as `HEALTHY` regardless of outcome.
  Fixed by additionally checking `resolved`/`reachable`/`valid` for an
  explicit `False`, the same boolean-success-key convention
  `MonitoringSyntheticExecutionService`'s own `_SUCCESS_KEYS` already
  used.
- **`MonitoringCollectionService` only ever gathers the pure-I/O
  collection phase concurrently — the same real concurrency bug
  `services/validation-service`'s own `ValidationExecutionService`
  already hit and fixed once, deliberately not repeated here.**
  `_collect_one` (calling a registered collector function) is safe to
  run inside `asyncio.gather()`, bounded by a semaphore
  (`max_parallel_collections`); `_persist_one` (every database write —
  metric series, health, availability, threshold/rule evaluation,
  event publication) always runs afterward in a plain sequential loop.
  `AsyncSession` is not safe for concurrent use by multiple asyncio
  tasks even for reads, since a flush is not reentrant.
- **Fourteen capabilities added beyond docs/044's literal 13-endpoint
  REST list**, the same "required capability, no REST list entry"
  precedent every prior AI-IOS service has established at least once:
  `POST /monitoring/metrics` and `GET /monitoring/metrics/{id}/series`
  (without them, no metric could ever be defined, and "Historical
  Queries"/"Time-window Analysis" — explicit "TIME SERIES" "Support"
  lines — would have no REST surface); `POST /monitoring/sla` and
  `POST /monitoring/slo` (without them, no SLA/SLO could ever be
  registered); `/monitoring-collectors`, `/monitoring-rules`,
  `/monitoring-dependencies`, `/monitoring-synthetic-tests`, and
  `/monitoring-retention-policies` (each GET+POST — without them,
  "Distributed Collectors"/"Dependency-aware Health"/"Synthetic
  Monitoring" — all explicit ACCEPTANCE CRITERIA lines — and
  "Retention Policies" would have nothing to configure them with); and
  `GET /monitoring/history` (`app/schemas/history.py`'s own
  `MonitoringHistoryResponse` was otherwise never referenced by any
  router — an orphaned-schema gap found via a coverage report, the
  same "found via coverage, wire it up" precedent
  `services/workflow-runtime-service`'s own `execution_step` endpoint
  already established).
- **`GET /monitoring/performance` and the `PERFORMANCE` report type
  are computed views, not their own table.** Docs/044's own 17-table
  list has no `monitoring_performance` table; "Performance Monitoring"
  is a live aggregation over `MonitoringMetricSeries` filtered to
  performance-relevant `MetricType` values (`LATENCY`, `IOPS`,
  `BANDWIDTH`, `PACKET_LOSS`), shared by `app/services/performance.py`
  between the direct API endpoint and the report generator.
- **Honest platform gap: scheduled collection runs have no caller
  identity.** No service-account/machine-credential mechanism has been
  established by any prior AI-IOS prompt, the same documented gap
  `services/workflow-runtime-service`'s own scheduled-instance trigger
  already accepts. Collectors that call another platform service
  (`inventory_asset`/`configuration_drift`/`workflow_instance`/
  `discovery_job`/`validation_posture`/`automation_job`) will receive a
  401 from that service until this gap is closed platform-wide; every
  native collector (`connectivity`/`port`/`dns`/`certificate`/`http`)
  is unaffected since it never calls another AI-IOS service at all.
- **A real Redis capacity limit hit once already, no further change
  needed here.** `services/validation-service` (the fourteenth
  service) exhausted Redis's default 16-logical-database limit,
  raising it to `--databases 32`; this service reuses that same
  headroom (test database `17`) with no infrastructure change of its
  own required.

## Running Locally

```bash
uv sync
# Requires the repository root docker-compose stack running (Postgres,
# Redis, RabbitMQ) -- see the repository root README. This service also
# needs its own database created once:
#   docker exec aiios_postgres psql -U aiios -d postgres \
#     -c "CREATE DATABASE aiios_monitoring OWNER aiios;"
uv run alembic upgrade head
uv run uvicorn main:app --reload --port 8015
```

Configuration is `AIIOS_`-prefixed environment variables via
`packages/shared-core/config` (see the repository root `.env.example`
for the shared `AIIOS_DATABASE_*`/`AIIOS_REDIS_*`/`AIIOS_RABBITMQ_*`
variables) plus this service's own `AIIOS_MONITORING_SERVICE_*`
variables (`app/config/settings.py`'s `MonitoringServiceSettings`):
`HOST`, `PORT` (default `8015`), `CORS_ALLOWED_ORIGINS`,
`JWT_PUBLIC_KEY_PATH`, `INVENTORY_SERVICE_BASE_URL`,
`DISCOVERY_SERVICE_BASE_URL`, `CONFIGURATION_SERVICE_BASE_URL`,
`AUTOMATION_SERVICE_BASE_URL`, `WORKFLOW_RUNTIME_SERVICE_BASE_URL`,
`VALIDATION_SERVICE_BASE_URL`, `HTTP_CLIENT_TIMEOUT_SECONDS`,
`DEFAULT_CHECK_TIMEOUT_SECONDS`, `MAX_PARALLEL_COLLECTIONS`,
`METRIC_RETENTION_DAYS`. Redis test database `17` — distinct from
every other AI-IOS service's own test database (... 15
workflow-runtime, 16 validation). Like every downstream AI-IOS
service, a missing JWT public key file is a hard startup error, never
silently regenerated.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET/POST /monitoring/targets` | Monitored target directory |
| `GET/POST /monitoring/metrics`, `GET .../{id}`, `GET .../{id}/series` | Reusable metric catalog and its own recorded time-series data |
| `GET /monitoring/health` | Health-check results for a target |
| `GET /monitoring/availability` | Uptime/downtime/maintenance intervals for a target |
| `GET /monitoring/performance` | Computed performance summary for a target (a view, not a table) |
| `GET/POST /monitoring/thresholds` | Threshold configuration for a metric |
| `GET/POST /monitoring/sla`, `GET/POST /monitoring/slo` | SLA/SLO objectives and their own tracked compliance |
| `GET /monitoring/reports` | Generate a report (8 types: health/availability/performance/capacity/executive/sla/slo/historical) |
| `GET /monitoring/statistics` | Organization-wide analytics rollup |
| `GET /monitoring/history` | Lightweight per-target historical health snapshots (added — see above) |
| `GET/POST /monitoring-collectors` | Distributed collector configuration (added) |
| `GET/POST /monitoring-rules` | Rule engine condition catalog (added) |
| `GET/POST /monitoring-dependencies` | Target dependency graph edges (added) |
| `GET/POST /monitoring-synthetic-tests` | Scheduled synthetic check configuration (added) |
| `GET/POST /monitoring-retention-policies` | Retention/downsampling policy configuration (added) |
| `GET /health` / `/readiness` / `/liveness` | Health checks (readiness includes Postgres connectivity) |
| `GET /metrics` | Prometheus metrics |
| `GET /docs` / `/openapi.json` | OpenAPI documentation |

Every endpoint requires valid authentication (`CurrentUserId`); tenant
isolation is enforced by every list/analytics query being scoped to
the `organization_id` the caller supplies, the same shape every prior
AI-IOS service established.

## Testing

```bash
uv run pytest --cov=app --cov-report=term-missing
```

266 tests, 98%+ coverage, entirely against real infrastructure (the
repository root's docker-compose Postgres/Redis/RabbitMQ) — no mocked
database. Postgres isolation between tests uses a per-test SAVEPOINT
(`join_transaction_mode="create_savepoint"`), the same pattern every
prior AI-IOS service established; `db_session_factory` is exposed
separately from `db_session` so worker/scheduler tests can build their
own `shared_core.database.factory.DatabaseFramework` sharing that same
test transaction (a scheduled job opens its own session, it doesn't
receive one via dependency injection). Real network collectors are
tested against a genuine local TCP server, a genuine local TLS server
presenting a freshly-generated self-signed certificate, and
`pytest-httpx` for HTTP checks (never a live external host); every
cross-service collector uses `pytest-httpx` against Inventory/
Discovery/Configuration Management/Automation/Workflow Runtime/
Validation's own real documented response shapes. The full app
lifespan — including a real `SchedulerManager` (leader election,
heartbeat, real Redis/RabbitMQ) — is exercised on every API-layer test
via `application.router.lifespan_context`, not skipped or mocked.
`test_service_collection.py`/`test_worker_collection.py` cover the
"Monitoring Engine" orchestrator end-to-end (every `collector_key`
dispatch branch, threshold/rule breach, broken-collector graceful
handling, and genuine scheduler-job failure propagation) with no
mocking of the orchestrator itself.

## Docker

Build from the **repository root** (this service is a uv workspace
member and its lockfile resolves against the whole workspace):

```bash
docker build -f services/monitoring-service/Dockerfile -t aiios/monitoring-service .
```

**Live health-check status**: mid-development, Docker Desktop's own
WSL2 port-forwarding layer became unstable on the development machine
(a container would report itself healthy and `docker inspect` would
show its port correctly published, yet the host could not actually
connect) — a host/environment issue, not something introduced by this
service's own code (`services/workflow-runtime-service`'s identical
real-`SchedulerManager`-per-test pattern runs without issue). Per
explicit direction, the live image build/health-check verification
against `aiios_aiios_network` is deferred until Docker Desktop's
networking stabilizes, rather than spending further time on
infrastructure troubleshooting outside this service's own code. The
image build itself (`docker build`, which needs no host networking)
was exercised successfully. Once infrastructure is stable, the
verification is: `/health`, `/readiness` (genuine Postgres connectivity
from inside the container), `/liveness`, `/docs`, `/openapi.json`, and
`/metrics` all responding correctly end-to-end through the
containerized app, plus a live unauthenticated request to
`/monitoring/targets` returning `401` — the same checks every prior
AI-IOS service's own Docker section already documents.

## Real bugs found via testing

1. **`MonitoringSyntheticExecutionService.run()` violated a real
   foreign key by passing `test.id` as `MonitoringMetricSeries
   .metric_id`.** A synthetic test's own id is never a metric's id;
   the first "record synthetic latency" integration test hit a genuine
   `ForeignKeyViolationError`. Fixed via
   `MonitoringMetricService.get_or_create_by_name`, lazily resolving
   one shared, reused `"synthetic_latency_ms"` metric per organization.
2. **The same service also violated a real foreign key by passing
   `test.id` as `MonitoringHealth.target_id` for a target-less
   synthetic test.** `MonitoringSyntheticTest.target_id` is nullable
   (a bare external endpoint may have no registered
   `MonitoringTarget`), but `MonitoringHealth.target_id` is not — the
   first target-less-test integration test hit the identical class of
   error. Fixed via `MonitoringTargetService.get_or_create`
   auto-registering a lightweight `CUSTOM_TARGET` row representing the
   test itself, resolved once via a new `_resolve_target_id` helper.
3. **`MonitoringCollectionService._persist_health_signal` silently
   recorded a failed DNS resolution as `HEALTHY`.** The breach-count
   check (`unresolved_drift_count`/`non_compliant_count`/
   `failed_count`) never matched a `dns` collector's own
   `{"resolved": false}` result shape, since those three field names
   belong to a different set of collectors sharing the same
   "no-numeric-value" persistence bucket. Fixed by additionally
   checking `resolved`/`reachable`/`valid` for an explicit `False`.
4. **A real integrity-constraint proof point, not a bug: every foreign
   key in this service's own 17-table schema is real and enforced.**
   Discovered as a *consequence* of writing genuine integration tests
   against real Postgres rather than a mocked session — every FK
   violation above surfaced immediately as a hard test failure with a
   precise `asyncpg.exceptions.ForeignKeyViolationError`, not a silent
   pass. No schema relaxation (e.g. making a column nullable to dodge
   the failure) was used to make a red test green; each was fixed at
   the service layer instead, preserving the schema's own real
   guarantees.

Every other mechanism — target/collector/metric/threshold/rule/sla/
slo/dependency/synthetic-test CRUD, real end-to-end collection runs
across every `collector_key` dispatch branch (single-metric,
named-metrics, health-signal, and delegated-automation), threshold and
rule breach evaluation, availability interval open/close/no-op
transitions, retention enforcement, statistics recomputation,
report generation across all 8 types, the recurring scheduler
registration (real `SchedulerManager`, real Redis/RabbitMQ), and every
notification/event/telemetry helper — was verified via real
integration tests against live Postgres/Redis/RabbitMQ (not mocks)
before this README was written, and found no further defects.
