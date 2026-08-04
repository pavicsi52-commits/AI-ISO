# AI-IOS Incident Management Service

Prompt 052. Correlation by fingerprint, priority-driven SLA clocks
against a configurable business calendar, an escalation ladder anchored
on the earliest breach, load- and skill-aware assignment, major-incident
declaration with a coordinated war room, root cause and problem
management with known errors, postmortems that refuse approval while
action items are unowned, and rolled-up statistics, generated reports,
and an append-only audit trail.

Runs on port **8023** against database **`aiios_incident_management`**
and Redis **db 25**.

---

## What this service is

This is where an outage becomes a coordinated response. Every trade-off
below exists because the cost of getting it wrong is measured in minutes
somebody spent unaware, or a page that never went out.

### Correlation is the point, not an afterthought

[`app/incidents/engine.py`](app/incidents/engine.py)'s `correlates()`
gates a recurring firing onto an existing open incident on three
conditions at once: a matching fingerprint, the existing incident still
open, and within an activity window. A thousand-host daily monitoring
sweep must update one incident per real problem, not raise a fresh one
every polling interval — and a closed incident that recurs must **reopen**
rather than duplicate, with its resolution fields cleared, because a
fix that did not hold must not survive the reopening it disproves.

### SLA clocks are stamped honestly, not invented

[`app/sla/engine.py`](app/sla/engine.py) skips starting a clock for any
SLA kind with no configured target — `DEFAULT_SLA_MINUTES` deliberately
has no entry for escalation SLAs. A clock that would never breach
against a made-up number is worse than no clock: it looks like a real
commitment on a dashboard and is not one. A breach's `breached_at` is
stamped at sweep time, not backdated to the clock's actual due date —
the escalation ladder's own anchor timing depends on this being honest
about *when the breach was discovered*, not when it technically occurred.

### The escalation ladder catches up, it doesn't trickle

[`app/escalation/engine.py`](app/escalation/engine.py)'s `due_steps()`
fires every overdue rung in one pass, anchored on the earliest breach
among an incident's SLA clocks. A sweep delayed by an outage of its own
catches up to where the ladder should be, rather than escalating one
level per tick and taking longer to reach the top the worse things get.

### Assignment prefers "reachable now" over "matches on paper"

[`app/assignment/engine.py`](app/assignment/engine.py)'s `assign()`
tries on-call before a skill match, deliberately: an on-call responder
who lacks the exact skill tag is still the person whose job is to be
reachable right now, and that beats a skill match that can be corrected
by reassignment once someone is actually looking. Ties within any tier
break on `responder_id`, so two responders at equal load resolve to the
same answer every time this runs.

### Impact reports the worst, not the average or the root

[`app/impact/engine.py`](app/impact/engine.py)'s `overall_impact()` takes
the worst reading among every affected service. Nineteen services at
MINOR and one at SEVERE is a severe incident; averaging would launder
the one thing that actually matters, and reporting only the root
service's own impact would miss a genuinely severe knock-on effect on
something the root service does not itself depend on being fine.

### A postmortem is only as good as its action items' ownership

`PostmortemService.transition` refuses to move a postmortem to
`APPROVED` while any action item remains unowned. A commitment nobody
owns is not a commitment, and approval is where that gets caught —
before publication, not after, when catching it is somebody else's
problem.

---

## Layout

| Path | What lives there |
| --- | --- |
| [`app/incidents/`](app/incidents/) | Pure fingerprinting, correlation, lifecycle transitions, MTTA/MTTR, percentiles |
| [`app/sla/`](app/sla/) | Pure business-calendar arithmetic, elapsed/breach/warning computation, pause accounting |
| [`app/escalation/`](app/escalation/) | Pure escalation ladder policy and due-step computation |
| [`app/assignment/`](app/assignment/) | Pure assignment policy: on-call, skill-based, load-balanced |
| [`app/impact/`](app/impact/) | Pure impact rollup and risk banding |
| [`app/models/`](app/models/) | 23 tables |
| [`app/repositories/`](app/repositories/) | 23 repositories, `require_in_org` named apart from the base's unscoped `require_by_id` |
| [`app/services/`](app/services/) | 9 services — the only layer touching infrastructure |
| [`app/api/`](app/api/) | 54 paths, 60 business operations, no single shared prefix — see `app/api/__init__.py` |
| [`app/workers/`](app/workers/) | SLA sweep, escalation sweep, statistics rollup, maintenance sweep — all leader-elected |

---

## Running it

```bash
docker build -t aiios/incident-management-service:0.1.0 \
  -f services/incident-management-service/Dockerfile .

docker run -d --name aiios_incident_management \
  --network aiios_aiios_network -p 8023:8023 \
  -e AIIOS_DATABASE_HOST=aiios_postgres -e AIIOS_DATABASE_PORT=5432 \
  -e AIIOS_DATABASE_NAME=aiios_incident_management \
  -e AIIOS_DATABASE_USER=aiios -e AIIOS_DATABASE_PASSWORD=change-me \
  -e AIIOS_REDIS_HOST=aiios_redis -e AIIOS_REDIS_DB=25 \
  -e AIIOS_REDIS_PASSWORD=change-me \
  -e AIIOS_RABBITMQ_HOST=aiios_rabbitmq -e AIIOS_RABBITMQ_USER=aiios \
  -e AIIOS_RABBITMQ_PASSWORD=change-me -e AIIOS_RABBITMQ_VHOST=/aiios \
  aiios/incident-management-service:0.1.0
```

`GET /readiness` reports both PostgreSQL and Redis. Migrations:
`uv run alembic upgrade head`. `keys/jwt_public_key.pem` is the public
half of `services/authentication-service`'s signing key — this service
verifies but never issues tokens.

### Two foreign keys have no valid `CREATE TABLE` order

`incidents.major_incident_id` points at `incident_major_events`, whose
own `incident_id` points back at `incidents`; the same is true of
`incidents.root_cause_id` and `incident_root_causes.incident_id`. Both
are declared with `use_alter=True` on the `Incident` side, deferring the
constraint to a post-create `ALTER TABLE` so the migration has an order
to run in at all.

---

## Tests

337 tests, **95.42%** branch coverage, against real PostgreSQL, Redis,
and RabbitMQ — including job registration against a real
`SchedulerManager` and all four workers' `tick()` methods against real
rows, not simulated ones.

```bash
uv run python -m pytest -q --cov=app --cov-branch --cov-fail-under=95
```

### A worker's own session is not the fixture's session

Every worker opens its own session per tick — production behaviour,
reproduced in tests via the same SAVEPOINT-bound `db_session_factory`
every other fixture shares. Re-reading a row a worker just committed
through the *fixture's* session (rather than a fresh one) returns that
session's stale, pre-tick identity-mapped copy — a plain SQLAlchemy
identity-map fact, not a bug, but one worth knowing before trusting a
test that quietly compares an object to itself.

### The one thing the HTTP tests cannot tell you

The `app` fixture overrides only the request session, so a test's writes
roll back — which changes **transaction lifetime**, and anything
depending on transaction lifetime is untestable there. `AuditService
.record_failure` commits in its own `session_scope` so a refused
request's audit entry survives the rollback of the request that raised;
under the SAVEPOINT that distinction vanishes and the test would pass
either way. Tested at service level against the real session factory
instead, the same way Prompts 049–051 test the analogous case.

---

## Notes worth keeping

- **A singleton-role check that passed still hit a duplicate-key
  error.** `assign_role`'s guard only rejected assigning a singleton war
  room role (incident commander, communication lead, technical lead,
  business lead) to someone *else* — reassigning the same person to the
  same role passed the check and then unconditionally inserted a second
  row, colliding with the table's own `(organization_id, war_room_id,
  participant_id, role)` uniqueness constraint. The same gap existed for
  every *non*-singleton role too, since those skipped the check
  entirely. Fixed to return the existing row when the exact triple
  already exists, for every role, not just singleton ones.
- **A war room could never actually be found stale.** Every war room is
  created `WarRoomStatus.OPEN`; nothing ever transitions one to
  `ACTIVE`. `WarRoomRepository.list_stale` filtered for `ACTIVE` alone,
  so the idle-war-room maintenance sweep could not have matched a single
  row it was written to catch. Caught while wiring the sweep itself, not
  by a test written after the fact.
- **Declaring a major incident opened a war room the API then had no
  way to find.** `MajorIncidentResponse` carries the declaration alone;
  nothing else on an incident's record names its war room's id.
  `GET /major-incidents/{incident_id}/war-room` closes the gap.
- **A route pinned to `PlainTextResponse` 500ed on its own JSON
  default.** `GET /reports/{report_id}/download` needs `text/csv` and
  `text/markdown` for two of its three formats, and setting
  `response_class=PlainTextResponse` at the route level to get those
  handed the endpoint's default JSON branch's Pydantic model straight to
  a renderer that only accepts `str`/`bytes` — `AttributeError: 'dict'
  object has no attribute 'encode'`. Fixed by dropping the route-level
  `response_class` and returning an explicit `PlainTextResponse` from
  the two branches that need one, letting FastAPI's default JSON
  handling take the third.
- **A loop variable's name outlived the loop.** `StatisticsService
  .rollup` used `row` for `Incident` in a `for row in created` loop,
  then reused `row` afterward for the unrelated `IncidentStatistic`
  being built. Only MyPy — blocked from running locally by Windows Smart
  App Control, so only caught once Docker recovered — flagged that the
  second assignment didn't match the type the name had already committed
  to. Renamed to `window`.
