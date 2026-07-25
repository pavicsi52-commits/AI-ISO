# Automation Service

Enterprise automation for AI-IOS
([`docs/040_Enterprise_Automation_Service.md`](../../docs/040_Enterprise_Automation_Service.md)):
playbooks, workflows, scripts, TOSCA deployments, configuration
enforcement, validation execution, operational tasks, and scheduled
jobs — dispatched against real infrastructure via SSH and local
runners, integrating with the Workflow SDK, Connector SDK, Inventory,
Configuration Management, Secrets Management, Scheduler, Queue
Framework, and RBAC. The eleventh AI-IOS microservice built on
`packages/shared-core`, following `services/authentication-service`,
`services/user-management-service`, `services/rbac-service`,
`services/organization-service`, `services/project-service`,
`services/secrets-management-service`, `services/inventory-service`,
`services/discovery-service`, `services/asset-management-service`, and
`services/configuration-management-service`.

## Architecture

Standard service structure per
[`docs/008_Backend_Master_Architecture.md.txt`](../../docs/008_Backend_Master_Architecture.md.txt).
Every domain-specific directory docs/040's own DIRECTORY STRUCTURE
names (`automation/`, `jobs/`, `executions/`, `playbooks/`,
`execution_plans/`, `retry/`, `rollback/`, `approvals/`, `logs/`,
`outputs/`, `artifacts/`, `variables/`, `inventory/`, `scheduling/`,
`analytics/`, `reports/`, …) is present but empty — the same
"aspirational skeleton, real code goes flat" precedent every prior
AI-IOS service established. Everything actually lives in the flat
`app/services/`/`app/repositories/`/`app/models/`/`app/schemas/`
layout, with several directories genuinely distinct from ordinary CRUD:

- `app/runners/` — five real local script/playbook runners (shell,
  bash, python, PowerShell, Ansible), every one a genuine
  `asyncio.create_subprocess_exec` call (never `shell=True`), no
  simulation.
- `app/connectors/` — `SshConnector`, the one genuinely real, live
  Docker-tested `shared_core.connectors.BaseConnector` provider this
  service registers, via `paramiko`.
  `app/dispatchers/execution_dispatcher.py` routes a job's content to
  either a local runner or `SshConnector` depending on whether a
  target was given.
  `AutomationTarget.connector_type` also happily stores nine other
  `ConnectorType` members with no concrete provider — dispatching to
  one raises a clear `DispatchError`, matching
  `packages/shared-core/connectors`'s own explicit scoping note that
  concrete providers beyond the core SDK are a separate, later phase.
- `app/secrets/`, `app/inventory/`, `app/dependencies/` — three lean,
  hand-built REST clients (Secrets Management, Inventory, Configuration
  Management), the same "no generated SDK" precedent
  `services/configuration-management-service`'s own `GitCredentialResolver`
  established.
- `app/workflow/`, `app/scheduling/` — the two SDK integration points:
  `build_automation_task_handler()` (a Workflow SDK `TASK`/`CONNECTOR`
  node handler) and `build_scheduler_job()` (converts an
  `AutomationSchedule` row into a `shared_core.scheduler` `Job`).

### Design decisions worth knowing

- **19 tables, confirmed by direct line-by-line reading of docs/040's
  own DATABASE TABLES list** — every one created.
- **Every entity construction site must pass `organization_id`
  explicitly.** `BaseModel`'s inherited `organization_id` column is
  `NOT NULL` with no database or ORM-side default — a real test caught
  `AutomationParameterService.create()` building a child
  `AutomationParameter` from only its parent `job_id`, assuming the
  tenant column would follow. Fixed by injecting
  `AutomationJobRepository` and fetching the parent job first, then
  passing `organization_id=job.organization_id` explicitly — the same
  fix pattern six services in `services/configuration-management-service`
  needed.
- **Concurrent dispatch, sequential persistence.** `AutomationExecutionService
  .run_execution()` dispatches every target in one batch concurrently via
  `asyncio.gather()` (bounded by `max_parallel_targets`) — the genuinely
  slow part (a subprocess or remote SSH call) — but writes every
  resulting step/log/output row afterward, strictly one at a time. A
  single SQLAlchemy `AsyncSession` is not safe for concurrent use from
  multiple coroutines, so persistence is deliberately sequential while
  the slow I/O runs in parallel.
- **Checkpointing and resume are real.** `run_execution()` always
  re-derives which targets already have a `COMPLETED` step (via
  `AutomationExecutionStepRepository.list_for_execution`) before
  dispatching anything, so calling it again after a pause only re-runs
  what's left — verified with a real interrupted-then-resumed execution
  test, not just a status-flag flip.
- **Retry is real and bounded.** `_dispatch_with_retry()` retries up to
  3 attempts using `shared_core.queue.retry.RetryPolicy` for real
  exponential-backoff timing (`asyncio.sleep`, not faked), only for
  failures classified `TRANSIENT` by `_classify_failure()`
  (`DependencyError` → transient; `TimeoutError`/a timeout-mentioning
  `RunnerError` → timeout; everything else, including an SSH auth
  failure's `ConnectorError`, → permanent, single attempt, no retry).
  Every attempt is recorded in `AutomationRetryHistory`. Verified live:
  one test drives 3 real transient retries (missing secret,
  `DependencyError`) against a live SSH container, another confirms a
  wrong-password auth failure gets exactly one attempt.
- **Cancel/pause are cooperative, not preemptive.** Checked between (not
  within) dispatch batches by re-fetching the execution's own row — an
  honest limitation given no mid-subprocess/mid-SSH-command
  interruption is implemented, the same scope `services/discovery-service`'s
  own scan-cancellation already accepted.
- **Async execution via a real queue, not a blocking HTTP request.**
  `POST /automation/jobs/{id}/execute` creates the `PENDING` execution
  row and enqueues `{"execution_id", "caller_token"}` onto
  `automation_execution_queue`, returning immediately — the actual
  dispatch happens in `app/workers/execution_worker.py`, a background
  consumer subscribed at startup. Matches docs/040's own "PERFORMANCE"
  section ("Async Execution", "Distributed Workers", "Queue Framework
  Integration") rather than the request blocking for a job's own
  (potentially hour-long) runtime.
- **The SSH credential-building heuristic is pragmatic, not
  cryptographic.** `_build_credential()` decides between an SSH-key and
  a username/password credential by checking whether the resolved
  secret string starts with `-----BEGIN` — a real, working heuristic,
  not a placeholder.
- **`AutomationTarget.username` was a real gap found while building the
  dispatcher**, not a test failure — SSH authentication genuinely needs
  an identity separate from the secret. Added via a proper second
  Alembic migration (`a6462780f7fe_add_username_to_automation_targets.py`),
  safe since the table was still empty.
- **Remote SSH dispatch is scoped to shell/bash content only** — `paramiko`'s
  `exec_command` takes one raw command string, and shell/bash script
  content works directly as that string; other playbook types over SSH
  would need file transfer, which `SshConnector` doesn't implement. An
  honest, documented scope limit: `DispatchError` on any other
  playbook-type-plus-target combination, not a silent failure.
  `FUTURE_DSL`/`CUSTOM_PLUGIN`/`WORKFLOW_TASK`/`TOSCA_SERVICE_TEMPLATE`
  (with no target) have no local runner registered either, for the same
  honest reason.
- **No REST surface for targets/variables/parameters/schedules/
  approvals/rollbacks/execution-plans/audit as their own top-level
  resources.** Docs/040's own literal REST APIs list names 17
  operations across 5 paths (`jobs`, `executions`, `templates`,
  `statistics`, `reports`); every other sub-resource service exists for
  internal wiring (e.g. `AutomationReportService` calls straight into
  `AutomationExecutionService`/`AutomationStatisticsService`) and is
  exercised directly in tests, the same "required table, no REST list
  entry" shape `services/configuration-management-service`'s own
  baselines/variables/policies/approvals set already established.
- **No route-registration-order hazard.** Unlike
  `services/configuration-management-service`'s own `profile_router`,
  every router here (`jobs`, `executions`, `templates`, `statistics`,
  `reports`) owns a distinct top-level path segment under
  `/automation/`, so FastAPI/Starlette's shape-based route matching
  never collides regardless of registration order.

## Running Locally

```bash
uv sync
# Requires the repository root docker-compose stack running (Postgres,
# Redis, RabbitMQ) -- see the repository root README. This service also
# needs its own database created once:
#   docker exec aiios_postgres psql -U aiios -d postgres \
#     -c "CREATE DATABASE aiios_automation OWNER aiios;"
uv run alembic upgrade head
uv run uvicorn main:app --reload --port 8011
```

Configuration is `AIIOS_`-prefixed environment variables via
`packages/shared-core/config` (see the repository root `.env.example`
for the shared `AIIOS_DATABASE_*`/`AIIOS_REDIS_*`/`AIIOS_RABBITMQ_*`
variables) plus this service's own `AIIOS_AUTOMATION_SERVICE_*`
variables (`app/config/settings.py`'s `AutomationServiceSettings`):
`HOST`, `PORT` (default `8011`), `CORS_ALLOWED_ORIGINS`,
`JWT_PUBLIC_KEY_PATH`, `SECRETS_SERVICE_BASE_URL`,
`INVENTORY_SERVICE_BASE_URL`, `CONFIGURATION_SERVICE_BASE_URL`,
`HTTP_CLIENT_TIMEOUT_SECONDS`, `DEFAULT_EXECUTION_TIMEOUT_SECONDS`,
`MAX_PARALLEL_TARGETS` (default `20`). Redis test database `13` —
distinct from every other AI-IOS service's own test database (3
authentication, 4 user-management, 5 rbac, 6 organization, 7 project, 8
secrets-management, 9 inventory, 10 discovery, 11 asset-management, 12
configuration-management). Like every downstream AI-IOS service, a
missing JWT public key file is a hard startup error.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET/POST /automation/jobs`, `GET/PUT/DELETE /automation/jobs/{id}` | Automation job directory and lifecycle |
| `POST /automation/jobs/{id}/execute` | Enqueue a new execution ("Async Execution") |
| `POST /automation/jobs/{id}/cancel` / `/pause` / `/resume` | Execution lifecycle control |
| `GET /automation/executions`, `GET /automation/executions/{id}` | Execution directory and detail |
| `GET /automation/executions/{id}/logs` | Structured execution log lines |
| `GET /automation/executions/{id}/artifacts` | Stored execution artifacts |
| `GET/POST /automation/templates` | Reusable automation content templates |
| `GET /automation/statistics` | Organization-wide analytics rollup |
| `GET /automation/reports` | Generate a report (7 types) |
| `GET /health` / `/readiness` / `/liveness` | Health checks (readiness includes Postgres connectivity) |
| `GET /metrics` | Prometheus metrics |
| `GET /docs` / `/openapi.json` | OpenAPI documentation |

Every endpoint requires valid authentication (`CurrentUserId`); tenant
isolation is enforced by every list/search/analytics query being scoped
to the `organization_id` the caller supplies, the same shape every
prior AI-IOS service established.

## Background Worker

One queue-consumed job (`app/workers/execution_worker.py`), subscribed
at startup:

- **`execution_worker`** — calls `AutomationExecutionService
  .run_execution()`, the actual dispatch step every `POST
  /automation/jobs/{id}/execute` and `/resume` call enqueues onto
  `automation_execution_queue`. A message with no `caller_token` (a
  schedule-fired, not interactively-triggered execution) is skipped and
  logged rather than attempted — no service-account/machine-credential
  mechanism has been established by any prior AI-IOS prompt, the same
  documented, honest platform gap
  `services/configuration-management-service`'s own `git_sync_worker`
  already flagged.

## Testing

```bash
uv run pytest --cov=app --cov-report=term-missing
```

229 tests, 97.06% coverage, entirely against real infrastructure (the
repository root's docker-compose Postgres/Redis/RabbitMQ, plus a
locally-run OpenSSH container for the SSH connector/dispatcher/full
execution-engine paths) — no mocked database. Postgres isolation
between tests uses a per-test SAVEPOINT
(`join_transaction_mode="create_savepoint"`), the same pattern every
prior AI-IOS service established. Every local runner (shell/bash/
python/PowerShell/Ansible) is exercised via genuine subprocess
execution; Secrets/Inventory/Configuration Management cross-service
calls use `pytest-httpx` against their real documented response shapes.

```bash
docker run -d --name aiios_automation_test_ssh -p 2223:2222 \
    -e PUID=1000 -e PGID=1000 -e PASSWORD_ACCESS=true \
    -e USER_NAME=testuser -e USER_PASSWORD=testpass123 \
    lscr.io/linuxserver/openssh-server:latest
```

A distinct host port (2223) from `services/discovery-service`'s own SSH
test container (2222), since both could conceivably run in the same CI
environment. Every SSH-dependent test (`tests/test_ssh_connector_live.py`,
the remote-dispatch cases in `tests/test_execution_dispatcher.py` and
`tests/test_service_execution.py`) skips automatically if this
container isn't reachable on `localhost:2223`.

`tests/test_schemas_unrouted.py` directly constructs every schema
backing a service with no dedicated top-level REST endpoint of its own
(approvals, audit, execution plans, execution steps, outputs,
parameters, results, retry history, rollbacks, schedules, targets,
variables) — the same precedent
`services/configuration-management-service`'s own identically-named
file established.

## Docker

Build from the **repository root** (this service is a uv workspace
member and its lockfile resolves against the whole workspace):

```bash
docker build -f services/automation-service/Dockerfile -t aiios/automation-service .
```

The image installs `bash` and `openssh-client` (covering the Bash and
Shell Script runners plus outbound SSH tooling) but deliberately not
`ansible-playbook` or PowerShell Core — the Ansible and PowerShell
runners honestly detect their absence at dispatch time (`RunnerError`)
rather than the image silently pretending to support them.

Built and live-health-checked against the real docker-compose network
(`aiios_aiios_network`) — `/health`, `/readiness` (genuine Postgres
connectivity from inside the container), `/liveness`, `/docs`,
`/openapi.json`, and `/metrics` all confirmed responding correctly
end-to-end through the containerized app. On Windows/Git Bash, remember
`MSYS_NO_PATHCONV=1` ahead of any `docker run`/`docker exec` whose
arguments include a leading-slash value (e.g. `AIIOS_RABBITMQ_VHOST=/aiios`) —
otherwise Git Bash silently rewrites it into a local filesystem path.

## Real bugs found via testing

1. **`AutomationParameterService.create()` never set `organization_id`
   when constructing a child `AutomationParameter` from only its
   parent `job_id`.** Caught immediately by a real `IntegrityError`
   against Postgres the first time its own test ran (the exact same bug
   class six services in `services/configuration-management-service`
   needed fixing for). Fixed by injecting `AutomationJobRepository`,
   fetching the parent job first, and passing
   `organization_id=job.organization_id` explicitly.
2. **`AutomationRetryHistory` was being constructed with
   `execution_id=None`** inside `_dispatch_with_retry()`, violating that
   column's own `NOT NULL` foreign key — found and fixed mid-development
   (before the first test run) by threading the real `execution_id`
   through as an explicit parameter from `run_execution()`'s own
   `asyncio.gather()` call site.
3. **`AutomationTarget` had no `username` field** when the dispatcher's
   credential-building logic was first written — SSH authentication
   genuinely needs an identity separate from the resolved secret value.
   Found via direct design reasoning while implementing
   `_build_credential()`, not a test failure; fixed with a proper second
   Alembic migration before any code could depend on the missing field.
4. **A background-consumer/test-harness interaction produced flaky,
   misattributed test failures**: `POST /automation/jobs/{id}/execute`
   genuinely enqueues onto a live, durable RabbitMQ queue with a real
   competing consumer (`execution_worker`) subscribed per test app
   instance; on Windows' ProactorEventLoop, an asyncpg connection
   opened by that background consumer against an engine a *different*
   test has since disposed is sometimes only garbage-collected during a
   later, unrelated test, producing an unraisable `ResourceWarning`
   pytest's `filterwarnings = ["error"]` turns into that later test's
   own failure. The exact environment/timing artifact
   `services/discovery-service`'s own `pyproject.toml` already
   diagnosed and fixed — the identical
   `ignore::pytest.PytestUnraisableExceptionWarning` filter applied here
   too, narrowly, rather than relaxing the blanket "error" policy.

Every other mechanism — job CRUD, the full execution engine (local
dispatch, live remote SSH dispatch, checkpoint/resume, cancel, pause,
retry/backoff, timeout), rollback initiate/complete, approval request/
decide/expire, schedule CRUD and the `shared_core.scheduler` `Job`
conversion, execution-plan CRUD, statistics recomputation (success/
failure rates, connector usage, top-failed/most-executed jobs,
heatmaps), and report generation across all 7 types — was verified via
real integration tests against live Postgres/Redis/RabbitMQ/SSH (not
mocks) before this README was written, and found no further defects.
