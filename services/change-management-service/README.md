# AI-IOS Change Management Service

Prompt 053. Risk-scored change requests, a policy-driven multi-level
approval chain, Change Advisory Board review with quorum-checked voting,
a change calendar with recurring maintenance windows and blackout
periods, scheduling conflict detection, implementation tasks and
post-change validation gates, rollback planning and execution,
post-implementation reviews that refuse approval while any action item
is unowned, and rolled-up statistics, generated reports, and an
append-only audit trail.

Runs on port **8024** against database **`aiios_change_management`**
and Redis **db 26**.

---

## What this service is

Every change this service tracks touches something already running.
Every trade-off below exists because the cost of getting it wrong is a
production system left in an ambiguous state.

### CANCELLED, REJECTED, and CLOSED are true dead ends

[`app/changes/engine.py`](app/changes/engine.py)'s `ALLOWED_TRANSITIONS`
has no way out of any of the three. A change that needs to try again is
a *new* change, optionally linked to the old one by a `RELATED_TO`
relationship — not a reason to reopen a formal decision people already
acted on, the same reasoning Prompt 050's policy lifecycle and Prompt
052's postmortem lifecycle both apply.

### Deciding an approval chain does not, by itself, move a change past `PENDING_APPROVAL`

`ApprovalService.decide()` sets `approved_at` once a chain resolves
favorably, and only advances the change's *status* to `CAB_REVIEW` if
`cab_required` is set. Otherwise the change stays `PENDING_APPROVAL` —
`ChangeService.schedule()` is the move that actually leaves it behind.
`CabService.close_meeting()` follows the identical pattern for
`CAB_REVIEW`. Neither "approval decided" nor "CAB decided" is the same
fact as "ready to schedule," and collapsing them would make a report
that only reads status unable to tell an approved-but-unscheduled change
from one still waiting on its first approver.

### A single CAB rejection sinks the review regardless of every other vote

[`app/cab/engine.py`](app/cab/engine.py)'s `tally()` — one dissenting
board member is enough to fail a review; a vote-counting rule that lets
a rejection be outvoted defeats the reason CAB exists. Any conditional
vote (with no rejection) makes the outcome `CONDITIONAL`; only
all-approve reaches `APPROVE`. All-abstain with quorum technically met
decides nothing — an outcome of `None`, not a silent approval.

### Risk is scored by the worst signal, never the average

[`app/risk/engine.py`](app/risk/engine.py)'s `automated_score()` takes
the higher of the classic likelihood×impact matrix and the single worst
of six independent risk dimensions. A change that is a severe security
risk and minimal everything else is still a severe risk — averaging six
numbers would launder the one that actually matters.

### A rollback moves the change's status the moment it starts, not when it finishes

`RollbackService.start()` sets the change to `ROLLED_BACK` as soon as
execution begins — the rollback's own finer-grained status
(`PLANNED`/`IN_PROGRESS`/`COMPLETED`/`FAILED`) tracks the attempt itself
separately, the same distinction Prompt 052 draws between an incident's
own status and its SLA/escalation records. A failed rollback attempt
(`RollbackService.fail()`) leaves the change `ROLLED_BACK` regardless —
a rollback that did not go cleanly is still not a change that succeeded.

### A recurring calendar entry never permanently drifts off its anchor date

[`app/calendar/engine.py`](app/calendar/engine.py)'s `expand_occurrences`
computes every occurrence from the entry's *original* `starts_at`, never
from the previous occurrence. A monthly maintenance window on the 31st
clamps to the 28th in February, but must land back on the 31st the
moment March allows it — stepping from the last cursor instead would
compound that clamp forever.

### A post-implementation review refuses approval while any action item is unowned

`PirService.transition()`, moving to `APPROVED` — a commitment nobody
owns is not a commitment, and approval is where that gets caught, the
same rule Prompt 052 applies to a postmortem.

---

## Layout

| Path | What lives there |
| --- | --- |
| [`app/changes/`](app/changes/) | Pure lifecycle transition graph, CAB eligibility, duration derivation |
| [`app/risk/`](app/risk/) | Pure risk scoring: matrix score, six-dimension score, banding, effective-level override |
| [`app/approvals/`](app/approvals/) | Pure multi-level approval chain resolution |
| [`app/cab/`](app/cab/) | Pure CAB vote tallying and quorum |
| [`app/calendar/`](app/calendar/) | Pure recurrence expansion and availability |
| [`app/conflicts/`](app/conflicts/) | Pure window-overlap and shared-resource conflict detection |
| [`app/models/`](app/models/) | 22 tables |
| [`app/repositories/`](app/repositories/) | 21 repositories, `require_in_org` named apart from the base's unscoped `require_by_id` |
| [`app/services/`](app/services/) | 12 services — the only layer touching infrastructure |
| [`app/api/`](app/api/) | 66 routes, no single shared prefix — see `app/api/__init__.py` |
| [`app/workers/`](app/workers/) | Conflict sweep, approval-expiry sweep, statistics rollup, maintenance sweep — all leader-elected |

---

## Running it

```bash
docker build -t aiios/change-management-service:0.1.0 \
  -f services/change-management-service/Dockerfile .

docker run -d --name aiios_change_management \
  --network aiios_aiios_network -p 8024:8024 \
  -e AIIOS_DATABASE_HOST=aiios_postgres -e AIIOS_DATABASE_PORT=5432 \
  -e AIIOS_DATABASE_NAME=aiios_change_management \
  -e AIIOS_DATABASE_USER=aiios -e AIIOS_DATABASE_PASSWORD=change-me \
  -e AIIOS_REDIS_HOST=aiios_redis -e AIIOS_REDIS_DB=26 \
  -e AIIOS_REDIS_PASSWORD=change-me \
  -e AIIOS_RABBITMQ_HOST=aiios_rabbitmq -e AIIOS_RABBITMQ_USER=aiios \
  -e AIIOS_RABBITMQ_PASSWORD=change-me -e AIIOS_RABBITMQ_VHOST=/aiios \
  aiios/change-management-service:0.1.0
```

`GET /readiness` reports both PostgreSQL (gating) and Redis
(non-gating). Migrations: `uv run alembic upgrade head`.
`keys/jwt_public_key.pem` is the public half of
`services/authentication-service`'s signing key — this service verifies
but never issues tokens.

Verified live against the real stack: created a change over HTTP,
submitted it, ran a risk assessment, read it back with the correct
derived `risk_level`/`cab_required`, and confirmed all three actions
landed in the append-only audit trail.

---

## Tests

498 tests, **97.13%** branch coverage, against real PostgreSQL, Redis,
and RabbitMQ — including job registration against a real
`SchedulerManager`, all four workers' `tick()` methods against real rows,
and real OTel spans read back from an in-memory exporter.

```bash
uv run python -m pytest -q --cov=app --cov-branch --cov-fail-under=95
```

### The one thing the HTTP tests cannot tell you

The `app` fixture overrides only the request session, so a test's writes
roll back — which changes **transaction lifetime**, and anything
depending on transaction lifetime is untestable there.
`AuditService.record_failure` commits in its own `session_scope` so a
refused request's audit entry survives the rollback of the request that
raised; under the SAVEPOINT that distinction vanishes and the test would
pass either way. Tested at service level against a second, independent
session opened from the real `db_session_factory`, the same way Prompts
049–052 test the analogous case.

---

## Notes worth keeping

- **Every span this service emitted was missing its own attributes.**
  `shared_core.telemetry.span.start_span`'s signature is
  `start_span(tracer, name, *, span_type=None, **attributes)` — there is
  no parameter literally named `attributes`, only the `**attributes`
  catch-all. Every `trace_*` function in `app/telemetry/tracing.py` was
  calling it as `start_span(tracer, name, span_type=..., attributes={...})`,
  which lands the whole dict as one entry, `{"attributes": {...}}`, inside
  that catch-all. `start_span` then tries `span.set_attribute("attributes",
  <dict>)`, which OpenTelemetry rejects outright (a dict is not a valid
  attribute value) and silently drops. Every span this service produced
  therefore carried `span.type` and nothing else — confirmed empirically
  against a real in-memory OTel exporter before and after. Fixed by
  unpacking each call site as `**{...}` instead of `attributes={...}`.
  **This is not unique to this service** — the identical pattern exists in
  23 other already-shipped AI-IOS services (every one after
  `authentication-service`, which does it correctly with `**attributes`);
  backfilling those is out of scope for this prompt but is a real,
  confirmed defect worth a dedicated pass.
- **A delegated approval step silently blocked its own chain from ever
  resolving.** `app/approvals/engine.py::level_status` counted a
  `DELEGATED` step (the closed-out original `ApprovalService.delegate`
  leaves behind) toward whether a level had unanimously resolved. A
  `DELEGATED` step is neither `REJECTED` nor `APPROVED`/`CONDITIONAL`, so
  a level containing one could never reach either resolution — even after
  the delegate approved — directly contradicting `delegate()`'s own
  docstring. Caught by a failing test asserting the delegate's decision
  still resolves the chain. Fixed by excluding `DELEGATED` steps before
  evaluating a level's rejection/approval.
- **A calendar entry loaded from the database crashed the occurrence
  expander.** Every other `Mapped[SomeEnum]` column in this codebase has
  an `X_of()` normaliser precisely because a freshly loaded row's enum
  column is a plain `str`, not the enum member — `RecurrenceKind` was the
  one column missing its normaliser.
  `ChangeCalendarRepository`-loaded entries' `entry.recurrence` (a plain
  `"none"`/`"daily"`/etc.) went straight into
  `app/calendar/engine.py::expand_occurrences`, which does
  `if recurrence is RecurrenceKind.NONE` — an identity check that a raw
  string can never satisfy — and `_STEP_FOR[recurrence]`, which then
  raises `KeyError: 'none'` for the non-`NONE` branch instead. Caught by
  two failing tests in `test_calendar_service.py` before the fix. Fixed
  by adding `recurrence_kind_of()` to `app/models/enums.py` (matching
  every sibling normaliser) and calling it in
  `CalendarService.list_occurrences_in_range` before handing
  `entry.recurrence` to the pure engine.
