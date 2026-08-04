# AI-IOS Enterprise Scheduler Service

Prompt 054. Distributed job scheduling -- cron, calendar, interval,
one-time, event-driven, and dependency-driven triggers, priority-based
dispatch with escalation, fixed/linear/exponential retry policies with a
dead letter path, manual failure recovery, maintenance windows and
holiday calendars that suppress and reshape dispatch, and rolled-up
statistics, generated reports, and an append-only audit trail.

Runs on port **8025** against database **`aiios_scheduler`** and Redis
**db 27**.

---

## What this service is

This is the platform's one clock. Every trade-off below exists because
the alternative was either reimplementing a scheduling primitive this
monorepo already has, or dispatching a job in a way this service cannot
actually make good on.

### This service dispatches; it never performs a job's own work

`ExecutionService.dispatch()`'s entire "unit of work" is publishing a
`JobStarted` event carrying the job's `payload` -- whichever platform
service owns that job's `job_type` (docs/054's own "PLATFORM
INTEGRATIONS": Automation, Workflow Runtime, Validation, Monitoring,
Compliance, Incident Management, Change Management, and more) is
presumed to act on it. A dispatch that successfully publishes is
recorded `COMPLETED`; this is a deliberate, documented scope boundary,
not an unfinished feature -- "Business-specific Scheduling Logic" is
explicitly out of scope for this prompt.

### Every scheduling primitive is reused, not reimplemented

Per this prompt's own instruction to "use every previously implemented
platform framework": [`app/scheduling/engine.py`](app/scheduling/engine.py)
delegates cron parsing and next-run computation straight to
`shared_core.scheduler.cron`/`.engine`; [`app/dependencies/engine.py`](app/dependencies/engine.py)'s
cycle detection is `shared_core.scheduler.dependency.DependencyGraph`'s
own depth-first search, not a second implementation; retry delay math in
[`app/retries/engine.py`](app/retries/engine.py) is
`shared_core.queue.retry.compute_backoff_delay` with the multiplier
pinned to `1.0` for a fixed delay, not a separate formula. The one
genuine gap the shared framework leaves is docs/054's own
`CalendarRuleKind` (daily/weekly/monthly/quarterly/yearly/business-days/
weekends) -- richer than `shared_core.scheduler.calendar`'s single
recurring weekly window -- and `calendar_rule_to_cron()` closes it by
*translating* into a cron expression rather than computing a due time
itself, so even that path still runs through the shared cron engine.

### Holiday-skipping is narrow on purpose

Only a `calendar`-type trigger whose rule is exactly `BUSINESS_DAYS`
gets its computed next run advanced past a configured holiday. A plain
`cron` trigger makes no promise about calendar days at all -- skipping a
nightly backup on a holiday because some other job happened to be
holiday-aware would be a silent, unrequested behaviour change for a
job that never asked for one.

### Maintenance-window suppression is one rule, applied uniformly

`kind` (`STANDARD`/`EMERGENCY`/`BLACKOUT`) is categorisation for
reporting. Every currently-active window suppresses dispatch the same
way; `allow_critical_override` is the one escape hatch, and it applies
identically regardless of `kind` -- simpler to reason about than a
kind-specific suppression matrix, and docs/054's "Override Rules" only
ever asks for one override mechanism, not several.

### Dependency-driven jobs are not blindly re-polled

The due-schedule sweep only ever considers triggers with a computed
`next_run_at` -- a `DEPENDENCY_DRIVEN` trigger's own computation is
always `None`. Re-checking every dependency-driven job's readiness on
every sweep tick with no dedup marker would risk dispatching it
repeatedly for as long as its parent stays in a satisfying status.
Today, a dependency-driven job dispatches through
`POST /scheduler/jobs/{id}/run` once a caller has confirmed readiness
via `GET .../dependencies` -- a documented scope boundary, not a bug.

---

## Layout

| Path | What lives there |
| --- | --- |
| [`app/scheduling/`](app/scheduling/) | Pure job/execution transition graphs, calendar-to-cron translation, next-due computation (thin adapter onto `shared_core.scheduler`) |
| [`app/dependencies/`](app/dependencies/) | Pure cycle detection (delegated), condition satisfaction, topological ordering |
| [`app/retries/`](app/retries/) | Pure retry delay computation (delegated) and dead-letter eligibility |
| [`app/priorities/`](app/priorities/) | Pure escalation-due checking and queue ordering |
| [`app/models/`](app/models/) | 15 tables |
| [`app/repositories/`](app/repositories/) | 15 repositories, `require_in_org` named apart from the base's unscoped `require_by_id` |
| [`app/services/`](app/services/) | 11 services -- the only layer touching infrastructure |
| [`app/api/`](app/api/) | 46 routes under `/scheduler/*`, no single shared prefix -- see `app/api/__init__.py` |
| [`app/workers/`](app/workers/) | Due-schedule sweep, retry sweep, statistics rollup, maintenance sweep -- all leader-elected |

---

## Running it

```bash
docker build -t aiios/scheduler-service:0.1.0 \
  -f services/scheduler-service/Dockerfile .

docker run -d --name aiios_scheduler \
  --network aiios_aiios_network -p 8025:8025 \
  -e AIIOS_DATABASE_HOST=aiios_postgres -e AIIOS_DATABASE_PORT=5432 \
  -e AIIOS_DATABASE_NAME=aiios_scheduler \
  -e AIIOS_DATABASE_USER=aiios -e AIIOS_DATABASE_PASSWORD=change-me \
  -e AIIOS_REDIS_HOST=aiios_redis -e AIIOS_REDIS_DB=27 \
  -e AIIOS_REDIS_PASSWORD=change-me \
  -e AIIOS_RABBITMQ_HOST=aiios_rabbitmq -e AIIOS_RABBITMQ_USER=aiios \
  -e AIIOS_RABBITMQ_PASSWORD=change-me -e AIIOS_RABBITMQ_VHOST=/aiios \
  aiios/scheduler-service:0.1.0
```

`GET /readiness` reports both PostgreSQL (gating) and Redis
(non-gating). Migrations: `uv run alembic upgrade head`.
`keys/jwt_public_key.pem` is the public half of
`services/authentication-service`'s signing key -- this service verifies
but never issues tokens.

Verified live against the real stack: created a job over HTTP, attached
a cron trigger, read back its computed `next_run_at`, manually dispatched
it (`COMPLETED`, `run_count` incremented), and confirmed both the
append-only audit trail and the live dashboard reflected it -- all
through the actual built image, with all four leader-elected background
jobs registering and one node acquiring scheduler leadership on startup.

---

## Tests

404 tests, **97.04%** branch coverage, against real PostgreSQL, Redis,
and RabbitMQ -- including job registration against a real
`SchedulerManager`, all four workers' `tick()` methods against real
rows, and real OTel spans read back from an in-memory exporter.

```bash
uv run python -m pytest -q --cov=app --cov-branch --cov-fail-under=95
```

### The one thing the HTTP tests cannot tell you

The `app` fixture overrides only the request session, so a test's writes
roll back -- which changes **transaction lifetime**, and anything
depending on transaction lifetime is untestable there.
`AuditService.record_failure` commits in its own `session_scope` so a
refused request's audit entry survives the rollback of the request that
raised; under the SAVEPOINT that distinction vanishes and the test would
pass either way. Tested at service level against a second, independent
session opened from the real `db_session_factory`, the same pattern
every prior AI-IOS service's own conftest establishes.

### A worker's own session is not the fixture's session

Every worker opens its own session per tick -- production behaviour,
reproduced in tests via the same SAVEPOINT-bound `db_session_factory`
every other fixture shares, since it is bound to the same underlying
connection.

---

## Notes worth keeping

- **A repository `.delete()` call passed the wrong type, three times.**
  `shared_core.database.repository.BaseRepository.delete()` takes an
  `entity_id: UUID`, not the entity object -- `TriggerService.remove()`,
  `DependencyService.remove()`, and `HolidayService.delete()` each
  called `self._repo.delete(stored)` (the full ORM row) instead of
  `self._repo.delete(stored.id)`. SQLAlchemy's own coercion layer caught
  it immediately and loudly (`ArgumentError: SQL expression element or
  literal value expected, got <... object>`) the moment a real test
  exercised any of the three `remove()`/`delete()` paths -- confirming a
  wrong-type argument to a repository method fails fast and clearly
  rather than silently, and that these three code paths had never
  actually been exercised until the test suite reached them. Fixed by
  passing `.id` at all three call sites.
- **`app/telemetry/tracing.py` was written correct from the start**,
  deliberately, after a sibling service's identical file was found to be
  silently dropping every span attribute (`start_span`'s signature is
  `start_span(tracer, name, *, span_type=None, **attributes)` -- no
  parameter is actually named `attributes`, so passing one as a literal
  keyword smuggles the whole dict into that catch-all under one bad key
  instead of spreading it). This service's own copy unpacks via
  `**{...}` at every call site and was confirmed correct by a real
  in-memory OTel exporter test, not just by not crashing.
- **A `calendar_config` value's type is asserted once, not scattered as
  `# type: ignore` comments.** `calendar_rule_to_cron()` reads
  caller-supplied `dict[str, object]` values (the column round-trips
  through JSON, so nothing in it is statically known to be
  `int`-constructible) -- an initial version silenced MyPy with
  `# type: ignore[arg-type]` at five call sites, which turned out not to
  even match the error code MyPy actually raised (`call-overload`, then
  `no-any-return` once corrected), each one a *second* MyPy error
  layered on the first. Replaced with one `_as_int()` helper that
  validates the value's real type and raises `ValidationError` for
  anything that isn't a whole number, rather than asserting the same
  untrue thing five times over.
