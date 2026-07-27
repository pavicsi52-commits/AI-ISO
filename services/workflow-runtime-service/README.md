# Workflow Runtime Service

Enterprise workflow runtime service for AI-IOS
([`docs/042_Enterprise_Workflow_Runtime_Service.md`](../../docs/042_Enterprise_Workflow_Runtime_Service.md)):
persistence, distributed dispatch, and a REST surface around
`packages/shared-core`'s own in-process DAG workflow engine (Prompt
028) — workflow definitions and semantic versioning, instance
execution/pause/resume/cancel/rollback/replay, checkpointing, human
approvals, compensation-based rollback, timers (cron/recurring),
event-driven triggers, and analytics/reporting. The thirteenth AI-IOS
microservice built on `packages/shared-core`, following
`services/authentication-service`, `services/user-management-service`,
`services/rbac-service`, `services/organization-service`,
`services/project-service`, `services/secrets-management-service`,
`services/inventory-service`, `services/discovery-service`,
`services/asset-management-service`,
`services/configuration-management-service`,
`services/automation-service`, and `services/playbook-service`.

## Architecture

Standard service structure per
[`docs/008_Backend_Master_Architecture.md.txt`](../../docs/008_Backend_Master_Architecture.md.txt).

**The SDK owns DAG execution, state machine, and structural node
types; this service owns everything else.** Research into
`packages/shared-core/src/shared_core/workflow/` (Prompt 028)
established a hard boundary before any code was written:
`WorkflowEngine`/`WorkflowManager`/`WorkflowRuntime` are purely
in-process and in-memory with no persistence hooks and no pause/resume
entry point. Of the SDK's 20 `NodeType` values, 9 structural ones
(`START`, `END`, `PARALLEL`, `MERGE`, `DELAY`, `TIMER`, `CONDITION`,
`SWITCH`, `SCRIPT`) are handled entirely by the engine itself; the
other 11 (`TASK`, `CONNECTOR`, `PLUGIN`, `AI`, `WEBHOOK`, `QUEUE`,
`EVENT`, `HUMAN_TASK`, `APPROVAL`, `LOOP`, `SUB_WORKFLOW`) are
delegated, requiring this service to register its own handler for each
one it supports (`app/handlers/`).

- `app/services/execution.py` — the central orchestrator.
  `WorkflowExecutionService.run_instance()` builds a `NodeHandlerRegistry`
  and a `CompensationRegistry`, sets `WorkflowContext.execution_id =
  str(instance.id)` (collapsing the SDK's own free-form execution
  identity onto this service's durable database identity), runs the
  compiled DAG for real via `engine.run()`, then persists every
  `WorkflowExecutionStep`/checkpoint/terminal event afterward — the
  engine itself is never made to await a database write mid-run.
- `app/services/checkpoint.py` — `CheckpointStore` (the SDK's own
  persistence hook) is a plain in-memory dict wrapper whose `save()`/
  `restore()` are called *synchronously*, never awaited. Real
  persistence works by buffering every checkpoint in a subclass
  (`PersistentCheckpointStore`) and flushing to Postgres only after
  `engine.run()` returns.
  `app/services/approval.py` — the SDK gives `APPROVAL`/`HUMAN_TASK`
  zero engine integration; `WorkflowApprovalService.wait_for_decision`
  is a real, DB-backed polling wait built entirely by this service, an
  explicitly **cooperative, not preemptive** mechanism (see below).
- `app/services/compensation.py` — `build_compensation_registry()` is
  shared by both automatic rollback (a failed run, inside
  `execution.py`) and manual rollback (`app/services/rollback.py`,
  reconstructing an in-memory `WorkflowExecution` from this service's
  own durable `WorkflowExecutionStep` rows before handing it to the
  same `shared_core.workflow.rollback.rollback_workflow` the engine
  itself uses).
- `app/scheduling/registrar.py` — maps a `WorkflowTimer` row
  (`CRON`/`RECURRING`) onto `shared_core.scheduler`'s own
  `Schedule`/`Job` shapes, the same "framework owns the loop, caller
  owns the job definitions" split `services/discovery-service`'s own
  `app/scheduling/registrar.py` already established.

### Design decisions worth knowing

- **A real, documented scope limit on replay.** Every replay always
  re-runs the *entire* compiled DAG from the top —
  `shared_core.workflow.WorkflowEngine.run()` gives no primitive for
  executing only a subset of an already-compiled plan. `FAILED_STEPS`
  and `FROM_CHECKPOINT` therefore only affect which *variables* seed
  the new run (a checkpoint's own `variables_snapshot`), never which
  *nodes* actually execute. Documented in `app/services/replay.py`'s
  own module docstring rather than silently implied.
- **Pause/resume/cancel are cooperative, metadata-only.** The SDK
  gives no true mid-run interrupt mechanism, and execution happens in
  a separate background worker process, not inline with the API
  request. `app/services/instance.py`'s own module docstring documents
  this rather than the endpoint implying a guarantee it can't keep.
- **`pause`/`resume`/`cancel`/`rollback`/`replay` under
  `/workflows/{id}/...` act on that definition's own most recent,
  still-active instance**, not the definition itself — the same
  interpretation docs/040's identically-shaped automation-service
  endpoints already established for this exact phrasing.
- **Two capabilities added beyond docs/042's literal 17-endpoint REST
  list**, the same "required capability, no REST list entry" precedent
  every prior AI-IOS service has established at least once:
  `POST /workflow-instances/{id}/approvals/{approval_id}/decide` and
  `GET /workflow-instances/{id}/approvals` (without them, Human
  Approvals — an explicit ACCEPTANCE CRITERIA line — would be entirely
  non-functional), and `GET /workflow-instances/{id}/steps` (per-node
  execution results were otherwise persisted but never exposed to any
  caller).
- **Honest platform gaps, not faked successes**, matching every prior
  AI-IOS service's discipline: `app/clients/playbook_client.py`'s
  Dependency Resolution and `app/clients/inventory_client.py`'s Label
  Resolution/Topology Queries call out that the target service exposes
  no such endpoint yet; `PLUGIN`/`AI` node types are left unregistered
  (no Plugin Marketplace/AI Assistant service exists yet); compensation
  actions are record-only (no automation-service endpoint exists to
  genuinely reverse an already-completed job execution).
- **Concurrency-safety discipline in the approval test suite.**
  `AsyncSession` is not safe for genuinely concurrent use by two
  asyncio tasks, so the tests never run
  `WorkflowApprovalService.wait_for_decision` concurrently with a
  second coroutine deciding the same approval over the same
  `db_session`. The approval mechanism is instead tested two safe
  ways: a full DAG run letting a short `timeout_seconds` genuinely
  expire, and a sequential decide-then-wait test (decide first, so the
  first poll iteration already finds it resolved).

## Running Locally

```bash
uv sync
# Requires the repository root docker-compose stack running (Postgres,
# Redis, RabbitMQ) -- see the repository root README. This service also
# needs its own database created once:
#   docker exec aiios_postgres psql -U aiios -d postgres \
#     -c "CREATE DATABASE aiios_workflow_runtime OWNER aiios;"
uv run alembic upgrade head
uv run uvicorn main:app --reload --port 8013
```

Configuration is `AIIOS_`-prefixed environment variables via
`packages/shared-core/config` (see the repository root `.env.example`
for the shared `AIIOS_DATABASE_*`/`AIIOS_REDIS_*`/`AIIOS_RABBITMQ_*`
variables) plus this service's own
`AIIOS_WORKFLOW_RUNTIME_SERVICE_*` variables
(`app/config/settings.py`'s `WorkflowRuntimeServiceSettings`): `HOST`,
`PORT` (default `8013`), `CORS_ALLOWED_ORIGINS`, `JWT_PUBLIC_KEY_PATH`,
`AUTOMATION_SERVICE_BASE_URL`, `PLAYBOOK_SERVICE_BASE_URL`,
`INVENTORY_SERVICE_BASE_URL`, `HTTP_CLIENT_TIMEOUT_SECONDS`,
`DEFAULT_WORKFLOW_TIMEOUT_SECONDS`, `APPROVAL_POLL_INTERVAL_SECONDS`,
`MAX_LOOP_ITERATIONS`. Redis test database `15` — distinct from every
other AI-IOS service's own test database (3 authentication, 4
user-management, 5 rbac, 6 organization, 7 project, 8
secrets-management, 9 inventory, 10 discovery, 11 asset-management, 12
configuration-management, 13 automation, 14 playbook). Like every
downstream AI-IOS service, a missing JWT public key file is a hard
startup error, never silently regenerated.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET/POST /workflows`, `GET/PUT/DELETE /workflows/{id}` | Workflow definition directory and lifecycle (each update bumps the semantic version) |
| `POST /workflows/{id}/execute` | Create a new instance and enqueue it for background dispatch |
| `POST /workflows/{id}/pause` / `/resume` / `/cancel` | Cooperative lifecycle control on the definition's own active instance |
| `POST /workflows/{id}/rollback` | Manual workflow/step rollback via compensation |
| `POST /workflows/{id}/replay` | Replay an instance as a new run (full / failed-steps / from-checkpoint) |
| `GET /workflow-instances`, `GET /workflow-instances/{id}` | Instance directory and detail |
| `GET /workflow-instances/{id}/logs` | Structured log lines for an instance |
| `GET /workflow-instances/{id}/steps` | Per-node execution results (added beyond docs/042's own REST list) |
| `GET /workflow-instances/{id}/checkpoints` | Persistent state snapshots |
| `GET /workflow-instances/{id}/approvals` / `POST .../approvals/{id}/decide` | Human approval history and decisions (added beyond docs/042's own REST list) |
| `GET /workflow/statistics` | Organization-wide analytics rollup |
| `GET /workflow/reports` | Generate a report (6 types) |
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

175 tests, 97.60% coverage, entirely against real infrastructure (the
repository root's docker-compose Postgres/Redis/RabbitMQ) — no mocked
database, and no mocking of `shared_core.workflow.WorkflowEngine.run()`
itself. Postgres isolation between tests uses a per-test SAVEPOINT
(`join_transaction_mode="create_savepoint"`), the same pattern every
prior AI-IOS service established. `TASK`/`CONNECTOR`/`WEBHOOK`
dispatch uses `pytest-httpx` against the Automation Service's own real
documented response shapes; `QUEUE` nodes and the execution worker use
a real RabbitMQ connection (`real_queue_framework`); the scheduler
registrar test uses a real `SchedulerManager` built from real
Redis/RabbitMQ. `tests/test_handlers.py` unit-tests every node
handler's own error path (missing `job_id`/`url`/`workflow_key`,
webhook request failure, loop `max_iterations` overflow) in isolation
rather than only through a full DAG run.

## Docker

Build from the **repository root** (this service is a uv workspace
member and its lockfile resolves against the whole workspace):

```bash
docker build -f services/workflow-runtime-service/Dockerfile -t aiios/workflow-runtime-service .
```

Built and live-health-checked against the real docker-compose network
(`aiios_aiios_network`) — `/health`, `/readiness` (genuine Postgres
connectivity from inside the container, `2.5ms`), `/liveness`,
`/docs`, `/openapi.json`, and `/metrics` all confirmed responding
correctly end-to-end through the containerized app; the container log
also showed a real `shared_core.scheduler` leader-election success
against live Redis/RabbitMQ at startup, and an unauthenticated request
to `/workflows` correctly returned `401`. On Windows/Git Bash,
remember `MSYS_NO_PATHCONV=1` ahead of any `docker run`/`docker exec`
whose arguments include a leading-slash value (e.g.
`AIIOS_RABBITMQ_VHOST=/aiios`) — otherwise Git Bash silently rewrites
it into a local filesystem path.

## Real bugs found via testing

1. **`instance.status.value` crashed with `AttributeError: 'str'
   object has no attribute 'value'` on a freshly loaded instance.**
   `WorkflowInstance.status` (like most enum-typed columns across this
   service, and across every prior AI-IOS service) is declared
   `Mapped[WorkflowInstanceStatus]` but backed by a plain `String(16)`
   column, not a real SQLAlchemy `Enum` type — so a value round-tripped
   through Postgres in a *different* session than the one that wrote it
   comes back as a bare `str`, not the enum member. This only ever
   surfaced through a genuine, separate-request HTTP round trip (a
   fresh `GET /workflow/reports?report_type=execution` hitting
   `_execution_report()`'s own DB read) — same-session unit tests never
   triggered it, since the in-memory object still held the enum it was
   originally assigned. Fixed at all 4 real call sites
   (`app/services/report.py`, `app/services/replay.py`,
   `app/services/instance.py`, `app/services/execution.py`) by
   switching `.value` to `str(...)` — safe because `WorkflowInstanceStatus`
   is a `StrEnum`, whose `str()` returns the same value whether the
   input is the enum member or the raw string a fresh DB read produces.
2. **24 completely empty, unreferenced scaffolding directories**
   (`app/logs`, `app/parallel`, `app/persistence`, `app/queue`,
   `app/replay`, `app/reports`, `app/rollback`, `app/runtime`,
   `app/scheduler`, `app/state_machine`, `app/timers`,
   `app/validators`, `app/variables`, `app/analytics`,
   `app/approvals`, `app/checkpoint`, `app/child_workflows`,
   `app/compensation`, `app/context`, `app/controllers`,
   `app/dispatcher`, `app/distributed`, `app/executor`) — each
   containing nothing but a zero-byte `__init__.py`, left over from
   initial scaffolding and never referenced by any import anywhere in
   `app/` or `tests/`. Found via a plain coverage-report read (every
   real package showed real statement counts; these showed `0 0 0 0
   100%`, the tell for a package with no code in it at all), confirmed
   dead with a repository-wide grep for each name, and deleted rather
   than left as clutter.
3. **`WorkflowExecutionStepResponse` (`app/schemas/execution_step.py`)
   was built and fully modeled but never wired to any endpoint** —
   0% coverage, the same "orphaned capability" shape this service's own
   `WorkflowEventRecord` table hit earlier in development. Per-node
   execution results were being persisted correctly by
   `app/services/execution.py` but were invisible to every caller.
   Fixed by adding `app/services/execution_step.py`
   (`WorkflowExecutionStepService`) and a new
   `GET /workflow-instances/{id}/steps` endpoint, wired through
   `app/api/deps.py` exactly like the sibling `logs`/`checkpoints`
   endpoints.
4. **`app/services/statistics.py`'s `recompute()` used `sum(await x
   for x in y)`** for `approval_count`/`replay_count` — Python treats a
   generator expression containing `await` as an async generator when
   defined inside an `async def`, so the sync builtin `sum()` raised
   `TypeError: 'async_generator' object is not iterable`. Fixed with
   explicit accumulator `for` loops.

Every other mechanism — workflow CRUD and semantic versioning, real
end-to-end DAG execution (linear happy path, task failure, automatic
rollback compensation, approval timeout, webhook dispatch, queue
dispatch, event publication, sub-workflow spawning), manual
rollback/replay, checkpointing, timers, and statistics/report
generation across all 6 report types — was verified via real
integration tests against live Postgres/Redis/RabbitMQ (not mocks)
before this README was written, and found no further defects.
