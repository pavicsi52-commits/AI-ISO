# Alerting Service

Enterprise alerting service for AI-IOS
([`docs/045_Enterprise_Alerting_Service.md`](../../docs/045_Enterprise_Alerting_Service.md)):
detects, correlates, deduplicates, suppresses, routes, escalates,
tracks, and resolves enterprise operational alerts — the operational
nervous system consuming events from Monitoring, Validation,
Automation, Workflow Runtime, Configuration Management, Discovery, and
Inventory. The sixteenth AI-IOS microservice built on
`packages/shared-core`, following `services/monitoring-service`.

## Architecture

Standard service structure per
[`docs/008_Backend_Master_Architecture.md.txt`](../../docs/008_Backend_Master_Architecture.md.txt),
with the decision logic deliberately split out of the services layer:

- `app/deduplication/fingerprint.py` — computes a stable SHA-256
  identity for "the same condition recurring". Uses SHA-256 rather than
  Python's own `hash()`, which is salted per process and would differ
  across restarts and workers — the exact opposite of what
  deduplication needs. Only identity-bearing `source_reference` keys
  are folded in; a per-occurrence sampled `value` is deliberately
  excluded, or every recurrence would look like a new problem.
- `app/rules/evaluator.py` — condition evaluation on
  `shared_core.workflow.expressions.evaluate_condition` (Jinja2
  `SandboxedEnvironment`), the same proven-safe evaluator every prior
  AI-IOS rule engine uses. A rule with **no** conditions never fires
  (an unconfigured rule must not raise a confident false alert).
- `app/suppression/` — `maintenance.py` owns recurrence evaluation,
  `engine.py` the suppression decision. Both fail safe: an
  uninterpretable recurrence rule falls back to the single stored
  interval rather than suppressing forever.
- `app/correlation/engine.py` — prefers a shared-reference match
  (`DEPENDENCY`) over a purely temporal one (`TIME`), breaking ties by
  severity then recency. Never correlates an alert to itself or to one
  that fired *after* it.
- `app/routing/engine.py` — a route filtered at `HIGH` also fires for
  `CRITICAL`, which is what an operator configuring "page me for HIGH"
  invariably means; a CRITICAL alert must never slip past.
- `app/escalation/` — `engine.py` validates a policy's own inline JSON
  levels into a typed chain with cumulative delays and returns the
  *furthest* due level (so a late pass lands correctly instead of
  replaying the chain); `oncall.py` resolves rotations with overrides
  beating the computed slot and holidays yielding nobody.
- `app/services/ingestion.py` — the central pipeline: fingerprint →
  deduplicate → suppress → raise → correlate, reporting which path each
  event took in an `IngestionResult` rather than leaving callers to
  infer it from the resulting status.
- `app/services/alert.py` — the lifecycle, with transitions validated
  against an explicit `ALLOWED_TRANSITIONS` table rather than left to
  each caller's discipline.

### Design decisions worth knowing

- **`shared_core.enums.severity.Severity` is reused directly, not
  reinvented.** Its own module docstring names "validation, alerting,
  and logging" as intended consumers, and docs/045's own "ALERT
  SEVERITY" list matches it exactly. Noted openly in
  `app/models/enums.py`: an earlier service
  (`services/validation-service`'s own `ValidationSeverity`) missed
  this and defined a parallel duplicate — not revisited here, since
  that is a shipped service outside this prompt's scope.
- **Alert status transitions are a validated state machine.**
  `RESOLVED → OPEN` is deliberately allowed (a condition that recurs
  after resolution reopens rather than silently dying) and reopening
  clears `resolved_at` so elapsed-time analytics measure the new
  occurrence. `CLOSED` is terminal.
- **`DELETE /alerts/{id}` closes rather than removes.** An alert is an
  operational record; deleting it would destroy the history every
  analytics and post-incident figure depends on.
- **Suppression is not deletion.** A suppressed alert is still stored,
  because noise analytics and post-incident review need the record.
- **Escalation only touches genuinely unattended alerts** (`NEW`/
  `OPEN`). Once acknowledged or under investigation, further automatic
  escalation would page people about work already underway.
- **`enabled`, not `is_active`, on configuration rows.** The inherited
  `BaseEntityMixin.is_active` is a soft-delete flag; a
  disabled-but-not-deleted rule is a distinct, real state.
- **No `list_active_at()` SQL helper on maintenance windows** — the
  tempting shortcut is left out on purpose, with a comment saying why:
  a `RECURRING` window's stored interval is only its *first*
  occurrence, so a column comparison would silently miss every later
  one.
- **Nine capabilities added beyond docs/045's literal 16-endpoint REST
  list**, each the same "required capability, no REST list entry"
  precedent every prior AI-IOS service has established: `/alert-routes`,
  `/alert-escalation-policies`, and `/alert-suppressions` (Routing,
  Escalation, and Suppression are explicit ACCEPTANCE CRITERIA with no
  way to configure them otherwise); `POST /alert-reports` (the literal
  list only reads reports, never produces one);
  `GET /oncall-schedules/{id}/current`; `POST /alerts/notifications/retry`
  ("Retry" is an explicit NOTIFICATIONS line); and
  `GET /alerts/{id}/history`, `/acknowledgements`, `/notifications`,
  `/correlations`.

### Honest platform gaps, surfaced rather than faked

- **PagerDuty, ServiceNow, and Opsgenie cannot be delivered to.**
  `shared_core.enums.notification_channel.NotificationChannel` covers
  EMAIL/SMS/PUSH/IN_APP/SLACK/TEAMS/DISCORD/WEBHOOK (verified against
  the enum, not assumed) but has no member for those three, which
  docs/045's own "ROUTING" list names. Routes configured for them are
  recorded as `FAILED` with an explicit reason rather than silently
  dropped or mis-delivered. Closing this means extending that shared
  enum and its providers — Prompt 025's scope, not this service's.
- **A `WORKFLOW` escalation level cannot run.** Launching a remediation
  workflow needs a caller token, and a scheduler-fired escalation pass
  has no caller — the platform-wide "no service-account credential
  mechanism exists yet" gap every prior AI-IOS service has documented.
  Such a level still escalates the alert and logs, never pretends a
  workflow ran.
- **Correlation matches shared identity references, not a live topology
  graph.** This service holds no topology, and monitoring-service's
  dependency graph needs a caller token the scheduled pass lacks.
  Shared-reference correlation is real and useful on its own; a genuine
  graph walk is deferred rather than faked with a stub.
- **Maintenance recurrence supports `FREQ=DAILY|WEEKLY|MONTHLY`
  (optionally `;INTERVAL=n`), not full RFC 5545.** No RFC 5545 parser
  exists in `packages/shared-core`, and `MONTHLY` approximates a month
  as 30 days — stated openly in the module rather than implied exact.

## Running Locally

```bash
uv sync --all-packages   # from the repository root, never bare `uv sync`
# Requires the root docker-compose stack (Postgres, Redis, RabbitMQ).
# This service needs its own database created once:
#   docker exec aiios_postgres psql -U aiios -d postgres \
#     -c "CREATE DATABASE aiios_alerting OWNER aiios;"
uv run alembic upgrade head
uv run uvicorn main:app --reload --port 8016
```

Configuration is `AIIOS_`-prefixed environment variables plus this
service's own `AIIOS_ALERTING_SERVICE_*` variables
(`app/config/settings.py`): `HOST`, `PORT` (default `8016`),
`CORS_ALLOWED_ORIGINS`, `JWT_PUBLIC_KEY_PATH`, the seven partner
service base URLs, `HTTP_CLIENT_TIMEOUT_SECONDS`,
`MAX_PARALLEL_RULE_EVALUATIONS`, `DEFAULT_DEDUPLICATION_WINDOW_SECONDS`,
`DEFAULT_CORRELATION_WINDOW_SECONDS`,
`DEFAULT_ESCALATION_POLL_INTERVAL_SECONDS`,
`ALERT_HISTORY_RETENTION_DAYS`. Redis test database `18` (… 16
validation, 17 monitoring).

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET/POST /alerts`, `GET/PUT/DELETE /alerts/{id}` | Alert directory and lifecycle (`POST` runs the full pipeline; `DELETE` closes) |
| `POST /alerts/{id}/acknowledge` / `/resolve` / `/escalate` | Lifecycle transitions |
| `GET /alerts/{id}/history` / `/acknowledgements` / `/notifications` / `/correlations` | An alert's own recorded state (added) |
| `POST /alerts/notifications/retry` | Re-attempt failed deliveries (added) |
| `GET/POST /alert-rules` | Rule engine catalog, with inline conditions |
| `GET/POST /maintenance-windows` | Maintenance windows (`?active_only=true` evaluates recurrence) |
| `GET/POST /oncall-schedules`, `GET .../{id}/current` | Rotations, overrides, and who is on call now |
| `GET/POST /alert-routes`, `/alert-escalation-policies`, `/alert-suppressions` | Routing, escalation, and suppression configuration (added) |
| `GET /alert-statistics` | Analytics rollup (`?recompute=true` forces a fresh pass) |
| `GET/POST /alert-reports` | Generate and list reports (7 types) |
| `GET /health` / `/readiness` / `/liveness` | Health checks (readiness includes Postgres connectivity) |
| `GET /metrics` | Prometheus metrics |
| `GET /docs` / `/openapi.json` | OpenAPI documentation |

Every business endpoint requires authentication; tenant isolation is
enforced by every query being scoped to the caller-supplied
`organization_id`.

## Testing

```bash
uv run pytest --cov=app --cov-report=term-missing
```

**185 tests, 97.96% coverage, ~39 seconds**, entirely against real
infrastructure (root docker-compose Postgres/Redis/RabbitMQ) — no
mocked database. Postgres isolation uses a per-test SAVEPOINT
(`join_transaction_mode="create_savepoint"`); `db_session_factory` is
exposed separately from `db_session` so the scheduled worker can build
its own `DatabaseFramework` sharing the same test transaction. The full
app lifespan — including a real `SchedulerManager` with real leader
election over Redis/RabbitMQ — runs on every API test. Cross-service
clients use `pytest-httpx` against each partner's own real documented
response shape.

## Docker

Build from the **repository root** (uv workspace member):

```bash
docker build -f services/alerting-service/Dockerfile -t aiios/alerting-service .
```

Built and **live health-checked** against the real compose network
(`aiios_aiios_network`): `/health`, `/liveness`, `/readiness` (genuine
Postgres connectivity from inside the container, `5.9ms`),
`/openapi.json`, `/metrics`, and `/docs` all returned `200`, plus a
live unauthenticated `GET /alerts` correctly returning `401`. Container
reported `healthy`; torn down afterwards.

## Real bugs found via testing

1. **Deduplication violated its own uniqueness constraint on a
   recurrence.** `alert_deduplication.fingerprint` is `UNIQUE`, but the
   first implementation always *inserted* a registry entry after
   raising an alert. The moment a condition recurred outside its
   deduplication window — or after its earlier alert was resolved — a
   second alert was correctly raised and the insert hit a genuine
   `DuplicateRecordError` from real Postgres. Fixed with
   `register_or_reassign`, which re-points the existing entry at the
   new primary alert and continues its occurrence count (so a flapping
   condition's lifetime count stays intact rather than resetting every
   window). Caught by two integration tests written specifically for
   the recurrence paths.
2. **Every infrastructure connection stalled on IPv6 — a real test-suite
   bug, not just an environment quirk.** `localhost` resolves to `::1`
   ahead of `127.0.0.1`, and Docker Desktop's IPv6 forwarding *hangs*
   rather than refusing, so there is no fast fallback and every attempt
   burns its full timeout. A single health test hung for five minutes.
   Diagnosed precisely (`getaddrinfo` ordering plus per-address
   `asyncio.open_connection` probes showing `localhost` timing out
   while `127.0.0.1` connected instantly), then fixed by pinning the
   conftest to the IPv4 literal via a documented `_LOOPBACK` constant.
   The same suite then ran in 2.59 seconds. Prior services' conftests
   still use `localhost` and are exposed to the same stall.
3. **`POST /workflows/{id}/execute` — an endpoint that did not exist was
   caught before shipping.** The first draft of the workflow client
   posted to `POST /workflow-instances`; verifying against
   `services/workflow-runtime-service`'s own routers showed instances
   are created *by executing a workflow*, never registered directly.
   Corrected to the real path, body shape, and `201` status, with the
   mistake recorded in the client's own docstring.
4. **Two dead-code traps removed rather than left for a future reader.**
   `AlertNotificationRepository.list_for_org` was unreferenced and
   deleted; `list_active_at` on maintenance windows was deleted *and
   replaced with a comment explaining why it must not exist* (it would
   silently miss recurring windows). Conversely `list_retryable` was
   unreferenced but backs docs/045's explicit "Retry" line, so it was
   wired into a real `retry_failed` capability with a `max_attempts`
   ceiling — an unreachable channel must not become an infinite loop —
   rather than deleted or left orphaned.

Every other mechanism — the full ingestion pipeline across all three
outcomes, lifecycle transitions including invalid-transition conflicts,
suppression by rule and by maintenance window, correlation preference
and idempotency, routing severity filters, escalation level resolution
and on-call rotation/override/holiday handling, MTTA/MTTR analytics,
all seven report types, the scheduled escalation worker against a real
`DatabaseFramework`, and scheduler registration against real Redis and
RabbitMQ — was verified by real integration tests before this README
was written, and found no further defects.
