# Validation Service

Enterprise validation service for AI-IOS
([`docs/043_Enterprise_Validation_Service.md`](../../docs/043_Enterprise_Validation_Service.md)):
verifies infrastructure readiness, operational health, configuration
correctness, compliance, connectivity, security posture, deployment
readiness, and runtime validation via reusable validation profiles, a
real Jinja2-sandboxed rule engine, weighted scoring, and remediation
suggestions. The fourteenth AI-IOS microservice built on
`packages/shared-core`, following `services/authentication-service`,
`services/user-management-service`, `services/rbac-service`,
`services/organization-service`, `services/project-service`,
`services/secrets-management-service`, `services/inventory-service`,
`services/discovery-service`, `services/asset-management-service`,
`services/configuration-management-service`,
`services/automation-service`, `services/playbook-service`, and
`services/workflow-runtime-service`.

## Architecture

Standard service structure per
[`docs/008_Backend_Master_Architecture.md.txt`](../../docs/008_Backend_Master_Architecture.md.txt),
mostly flat (`app/services/`/`app/repositories/`/`app/models/`/
`app/schemas/`/`app/api/`), with a handful of genuinely distinct
modules:

- `app/collectors/` — the data-gathering half of a check. Real,
  native network collectors (`network.py`: TCP connectivity/port
  checks, DNS resolution, TLS certificate expiry) run directly from
  this process; delegated collectors (`remote.py`) dispatch a live
  automation-service job for anything requiring genuine remote
  execution this service has no connectivity of its own to perform
  (disk/CPU/memory/processes/etc.); read-only collectors
  (`service_state.py`) read already-recorded state from Inventory,
  Configuration Management, Workflow Runtime, and Discovery.
- `app/rules/evaluator.py` — the pass/fail/warn logic half of a check,
  built on `shared_core.workflow.expressions.evaluate_condition` (a
  Jinja2 `SandboxedEnvironment`), the same proven-safe evaluator
  `shared_core.workflow`'s own conditional nodes already use, rather
  than a hand-rolled or `eval()`-based one.
- `app/scoring/engine.py` — the weighted scoring aggregator. No
  `shared_core` equivalent exists (confirmed: no weighted-scoring
  utility lives anywhere in `packages/shared-core`), so this is built
  directly on top of a completed execution's own results.
- `app/services/execution.py` — the orchestrator. Runs every
  `(check, target)` pair from a profile's own resolved `check_ids` ×
  an execution's own targets, respecting `concurrency_strategy`.

### Design decisions worth knowing

- **`PARALLEL`/`DISTRIBUTED` only ever run the collection phase
  concurrently — a real bug found and fixed during testing.** An
  early implementation ran the whole `(check, target)` pipeline —
  collection *and* database writes — inside one `asyncio.gather()`.
  `AsyncSession` is not safe for concurrent use by multiple asyncio
  tasks even for reads, and the very first parallel-execution test hit
  a genuine `SAWarning` from SQLAlchemy's own flush-process reentrancy
  guard. Fixed by splitting each check into a pure-I/O collection
  phase (`_collect_one`, safe to run concurrently — it never touches
  the database) and a database-writing persistence phase
  (`_persist_result`, always run afterward in a plain sequential
  loop, one at a time, regardless of `concurrency_strategy`). True
  multi-process "Distributed Execution" would need a worker pool this
  service doesn't have — an honest scope limit documented in
  `run_execution`'s own docstring rather than silently implied.
- **`/validations` and `/validation-profiles` front the identical
  underlying resource.** Docs/043's own literal REST list names both
  `/validations` (full CRUD plus `execute`/`cancel`) and
  `/validation-profiles` (`GET`/`POST` only) for what is, on every
  field and every acceptance-criteria line, the same "reusable, named
  collection of checks" concept (`ValidationProfile`) the doc's own
  "VALIDATION PROFILES" section describes exactly once. Rather than
  inventing a second, fake resource type, `/validations` is the full
  lifecycle resource (matching `services/workflow-runtime-service`'s
  own `/workflows`) and `/validation-profiles` is a second, lighter
  list/create surface over that identical resource.
- **A check only collects; a rule decides.** `ValidationCheck` and
  `ValidationRule` are deliberately two tables, not one — a check with
  zero rules attached always produces `UNKNOWN` (never a silent
  `PASSED`), and multiple rules may reference the same check at
  different thresholds (e.g. `WARNING` at 80% disk usage, `FAILED` at
  95%), evaluated in `priority` order, first match wins.
- **Four capabilities added beyond docs/043's literal 16-endpoint REST
  list**, the same "required capability, no REST list entry"
  precedent every prior AI-IOS service has established at least once:
  `/validation-categories`, `/validation-checks`, and
  `/validation-rules` (without them, there would be no way to
  populate the reusable check/rule catalog `/validations` itself
  depends on — "Rule Engine" is an explicit ACCEPTANCE CRITERIA line);
  and `GET /validation-results/executions/{id}` /
  `GET /validation-results/executions/{id}/score` (without them, a
  real, computed, persisted score — "Scoring" is also an explicit
  ACCEPTANCE CRITERIA line — would have no REST surface at all, the
  same "orphaned capability, found via coverage" gap
  `services/workflow-runtime-service`'s own `WorkflowEventRecord`
  table already hit once before). `/validation-results/failures/{id}
  /exceptions` (request/list/decide a waiver) was added the same way.
- **Honest platform gaps, not faked successes**, matching every prior
  AI-IOS service's discipline: `app/clients/configuration_client.py`
  reads only *already-recorded* drift/compliance evaluations (the real
  Configuration Management Service endpoints have no "compare live
  now" trigger); `app/clients/discovery_client.py` reads only a
  discovery job's own summary counts (`DiscoveryRelationshipService`
  exists internally in `services/discovery-service` but no REST
  router exposes it); topology/relationship checks instead read
  `services/inventory-service`'s own real `/inventory/topology`
  endpoint under the assumption that inventory is the system of
  record discovery ultimately writes into.
- **A real Redis capacity limit hit and fixed.** Redis defaults to 16
  logical databases (indices 0–15); by this, the fifteenth AI-IOS
  service to need its own isolated test database, every index was
  already spoken for. Fixed by adding `--databases 32` to the shared
  `docker-compose.yml` Redis service (a safe, additive change — lower
  indices are unaffected) rather than reusing another service's own
  test database.

## Running Locally

```bash
uv sync
# Requires the repository root docker-compose stack running (Postgres,
# Redis, RabbitMQ) -- see the repository root README. This service also
# needs its own database created once:
#   docker exec aiios_postgres psql -U aiios -d postgres \
#     -c "CREATE DATABASE aiios_validation OWNER aiios;"
uv run alembic upgrade head
uv run uvicorn main:app --reload --port 8014
```

Configuration is `AIIOS_`-prefixed environment variables via
`packages/shared-core/config` (see the repository root `.env.example`
for the shared `AIIOS_DATABASE_*`/`AIIOS_REDIS_*`/`AIIOS_RABBITMQ_*`
variables) plus this service's own `AIIOS_VALIDATION_SERVICE_*`
variables (`app/config/settings.py`'s `ValidationServiceSettings`):
`HOST`, `PORT` (default `8014`), `CORS_ALLOWED_ORIGINS`,
`JWT_PUBLIC_KEY_PATH`, `INVENTORY_SERVICE_BASE_URL`,
`CONFIGURATION_SERVICE_BASE_URL`, `AUTOMATION_SERVICE_BASE_URL`,
`WORKFLOW_RUNTIME_SERVICE_BASE_URL`, `DISCOVERY_SERVICE_BASE_URL`,
`HTTP_CLIENT_TIMEOUT_SECONDS`, `DEFAULT_CHECK_TIMEOUT_SECONDS`,
`MAX_PARALLEL_CHECKS`. Redis test database `16` — distinct from every
other AI-IOS service's own test database (3 authentication, 4
user-management, 5 rbac, 6 organization, 7 project, 8
secrets-management, 9 inventory, 10 discovery, 11 asset-management, 12
configuration-management, 13 automation, 14 playbook, 15
workflow-runtime) — required bumping the shared Redis container's own
`--databases` limit from its default 16 (see above). Like every
downstream AI-IOS service, a missing JWT public key file is a hard
startup error, never silently regenerated.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET/POST /validations`, `GET/PUT/DELETE /validations/{id}` | Validation profile directory and lifecycle (each update bumps the semantic version) |
| `POST /validations/{id}/execute` | Create a new execution and enqueue it for background dispatch |
| `POST /validations/{id}/cancel` | Cooperative cancellation of the profile's own active execution |
| `GET/POST /validation-profiles` | A lighter list/create surface over the identical profile resource |
| `GET/POST /validation-templates` | Reusable profile starting points |
| `GET /validation-results`, `GET /validation-results/{id}` | Per-check-per-target results and their own raw collected-data details |
| `GET /validation-results/executions/{id}` / `.../score` | An execution's own detail and weighted score (added beyond docs/043's own REST list) |
| `GET /validation-results/{id}/failures` | Failures recorded for a result |
| `POST/GET /validation-results/failures/{id}/exceptions`, `POST .../decide` | Request, list, and decide waivers for a known failure (added beyond docs/043's own REST list) |
| `GET/POST /validation-categories`, `/validation-checks`, `/validation-rules` | The reusable check/rule catalog (added beyond docs/043's own REST list) |
| `GET /validation/statistics` | Organization-wide analytics rollup |
| `GET /validation/reports` | Generate a report (7 types) |
| `GET/POST /validation/remediation`, `POST .../apply` | Remediation suggestions and applying them |
| `GET /health` / `/readiness` / `/liveness` | Health checks (readiness includes Postgres connectivity) |
| `GET /metrics` | Prometheus metrics |
| `GET /docs` / `/openapi.json` | OpenAPI documentation |

Every endpoint requires valid authentication (`CurrentUserId`); tenant
isolation is enforced by every list/analytics query being scoped to
the `organization_id` the caller supplies, the same shape every prior
AI-IOS service established. No route-registration-order hazard exists
here — docs/043's own singular-"validation" (`/validation/statistics`,
`/validation/reports`, `/validation/remediation`) vs.
plural-"validations" (`/validations`) naming keeps every router's own
prefix textually distinct.

## Testing

```bash
uv run pytest --cov=app --cov-report=term-missing
```

193 tests, 98.04% coverage, entirely against real infrastructure (the
repository root's docker-compose Postgres/Redis/RabbitMQ) — no mocked
database. Postgres isolation between tests uses a per-test SAVEPOINT
(`join_transaction_mode="create_savepoint"`), the same pattern every
prior AI-IOS service established. Real network collectors are tested
against a genuine local TCP server and a genuine local TLS server this
test suite starts itself, presenting a freshly-generated self-signed
certificate (never a live external host); every cross-service
collector uses `pytest-httpx` against Inventory/Configuration
Management/Automation/Workflow Runtime/Discovery's own real documented
response shapes. `test_service_execution.py` covers real end-to-end
execution runs (happy path, failing rule, unresolvable collector,
parallel concurrency, cooperative cancellation) with no mocking of the
orchestrator itself.

## Docker

Build from the **repository root** (this service is a uv workspace
member and its lockfile resolves against the whole workspace):

```bash
docker build -f services/validation-service/Dockerfile -t aiios/validation-service .
```

Built and live-health-checked against the real docker-compose network
(`aiios_aiios_network`) — `/health`, `/readiness` (genuine Postgres
connectivity from inside the container, `3.9ms`), `/liveness`,
`/docs`, `/openapi.json`, and `/metrics` all confirmed responding
correctly end-to-end through the containerized app, plus a live
unauthenticated request to `/validations` correctly returning `401`.
On Windows/Git Bash, remember `MSYS_NO_PATHCONV=1` ahead of any
`docker run`/`docker exec` whose arguments include a leading-slash
value (e.g. `AIIOS_RABBITMQ_VHOST=/aiios`) — otherwise Git Bash
silently rewrites it into a local filesystem path.

## Real bugs found via testing

1. **`PARALLEL`/`DISTRIBUTED` concurrency corrupted SQLAlchemy's own
   session state.** The first version of `run_execution()` ran each
   `(check, target)` pair's *entire* pipeline — collector I/O and
   database writes together — inside one `asyncio.gather()`. The very
   first parallel-execution test hit a genuine
   `sqlalchemy.exc.SAWarning: Usage of the 'Session.add()' operation
   is not currently supported within the execution stage of the flush
   process` — `AsyncSession` is not safe for concurrent use by
   multiple asyncio tasks, even within one single-threaded event loop,
   since a flush is not reentrant. Fixed by splitting collection
   (`_collect_one`, pure I/O, safe to gather concurrently) from
   persistence (`_persist_result`, always sequential); the semantics
   documented in `run_execution`'s own docstring so the next reader
   understands *why* the two phases are split rather than assuming
   it's an arbitrary refactor.
2. **`ValidationTemplate.created_by` silently redefined an inherited
   audit column.** `BaseEntityMixin` already reserves `created_by` for
   its own `UUID`-typed "who created this row" audit field; this
   model's own `created_by: str | None` (a free-text author display
   name) collided with it, a real type conflict MyPy caught
   immediately once unblocked. Renamed to `authored_by` across the
   model, service, schema, and API layer.
3. **`ValidationProfile.concurrency_strategy` was typed as a plain
   `str`, not the enum** — an inconsistency with every other
   enum-backed column in this service, caught by MyPy when
   `POST /validations/{id}/execute`'s own `body.concurrency_strategy
   or profile.concurrency_strategy` fallback tried to combine a real
   enum with a bare string. Fixed by properly typing the column
   `Mapped[ValidationConcurrencyStrategy]`, matching every sibling
   column's own convention, and removing the now-unnecessary `str()`
   coercions in `ValidationProfileService`.
4. **24 completely empty, unreferenced scaffolding directories** (13
   in `app/models`-adjacent locations plus a leftover `app/engine/`
   from an earlier draft before the collector/rules/scoring split was
   settled on) — the same "found via a plain coverage-report read,
   confirmed dead with a grep, deleted" precedent
   `services/workflow-runtime-service`'s own README already
   established for an identical class of leftover scaffolding.
5. **A rule engine "no rule = UNKNOWN" design decision, confirmed
   correct via test failure, not a bug.** The first draft of the
   happy-path end-to-end test asserted a connectivity check with zero
   attached rules would score `PASSED` — it scored `UNKNOWN` instead.
   This is `evaluate_rule_chain`'s own intended behavior (an absent
   rule is never silently a pass), not a bug; the test itself needed a
   real rule attached, fixed accordingly.

Every other mechanism — profile/template/category/check/rule/target
CRUD, real end-to-end DAG-free execution (sequential and parallel),
weighted scoring across all 6 named categories plus overall, failure
recording and exception (waiver) approval workflow, remediation
suggestion and apply tracking, and report generation across all 7
types — was verified via real integration tests against live
Postgres/Redis/RabbitMQ (not mocks) before this README was written,
and found no further defects.
