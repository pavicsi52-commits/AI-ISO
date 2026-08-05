# AI-IOS Enterprise Notification Center Service

Prompt 055. Centralized, persisted, multi-channel notification
delivery -- templates with versioning and preview, per-user
preferences and quiet hours, topic/role/project subscriptions, retry
with backoff and a dead-letter queue, delivery tracking through read
and acknowledged, announcements and broadcasts, digests, rolled-up
statistics, generated reports, and an append-only audit trail.

Runs on port **8026** against database **`aiios_notification_center`**
and Redis **db 28**.

---

## What this service is

Every prior AI-IOS service already sends its own best-effort
notifications via `shared_core.notifications` (Prompt 025) -- an
in-memory manager built fresh in each service's own app factory. This
is the platform's *central*, persisted version of the same framework:
one place a notification's full lifecycle (created, queued, sent,
delivered, read, acknowledged, retried, dead-lettered) is durable and
queryable, rather than living only in one process's memory until the
next restart.

### `shared_core.notifications` does the actual work; this service is the persistence and orchestration around it

Per this prompt's own "use every previously implemented platform
framework" instruction: template rendering
([`app/rendering/engine.py`](app/rendering/engine.py)) is a direct
pass-through to `shared_core.notifications.renderer`; retry delay math
([`app/retries/engine.py`](app/retries/engine.py)) is
`shared_core.queue.retry.compute_backoff_delay` plus
`shared_core.notifications.retry.classify_delivery_failure`; digest
grouping and deduplication
([`app/digest/engine.py`](app/digest/engine.py)) is
`shared_core.notifications.digest.build_digest`; actual channel I/O
goes through one process-wide `shared_core.notifications.manager
.NotificationManager`. The one genuine gap --
[`app/routing/engine.py`](app/routing/engine.py)'s preference-allow and
quiet-hours checks -- exists because this service's own channel/category
vocabulary (docs/055 names eleven channels and thirteen categories) is
deliberately richer than `shared_core`'s eight/fifteen, and
round-tripping every check through a lossy translation would be more
code than reimplementing three small, pure rules natively (see
`app/models/enums.py`'s own `to_shared_channel`/`to_shared_notification_type`
translators for exactly which values collapse together and why).

### A channel needs two separate "yes" before anything is attempted

`DeliveryService.dispatch()` resolves a notification's channels by
intersecting the *recipient's own preferences* (would they accept this
category over this channel, and are they in quiet hours) with the
*organization's own configuration* (has this channel been set up and
enabled at all). `EMAIL` and `IN_APP` are always organization-enabled
by this service's own rule -- every prior service already assumes
best-effort email is reachable, and in-app delivery is this service's
own always-on feed needing no external configuration. Every other
channel (`SMS`, `SLACK`, `TEAMS`, `DISCORD`, `WEBHOOK`, `MOBILE_PUSH`,
`BROWSER_PUSH`, `REST_CALLBACK`, `CUSTOM`) needs an explicit,
organization-owned `NotificationChannelConfig` row before it is ever
attempted -- a channel a user prefers but their organization never
configured is silently excluded from resolution, not attempted and
failed.

### This service's own in-app store, not `shared_core`'s

`shared_core.notifications.in_app.InAppChannel` is registered at
startup purely so a dispatch to `IN_APP` succeeds through the shared
framework's own dispatch path -- its backing
`InAppNotificationStore` is in-memory and immediately discarded. The
actual, durable "IN-APP NOTIFICATION CENTER" (docs/055: feed,
read/unread, search, filter, pagination) is this service's own
persisted `notifications`/`notification_deliveries` tables, read back
through `GET /notifications` and friends -- never `shared_core`'s
in-memory equivalent.

### Webhook-shaped channels resolve their URL per message, not per process

`SLACK`, `TEAMS`, `DISCORD`, and `WEBHOOK` all share one
`webhook_url_resolver` registered once at startup
([`app/core/factory.py`](app/core/factory.py)), but a static,
process-wide URL cannot vary per organization. Before dispatch,
`DeliveryService` looks up the organization's own configured URL and
embeds it into the outgoing `NotificationMessage.metadata`, which the
shared resolver simply reads back -- one resolver function, many
tenants.

### A notification's own status is a roll-up, never overwritten backwards

One notification can fan out into several `NotificationDelivery` rows
(one per resolved channel). `_recompute_notification_status()` derives
the notification's own status from all of its deliveries' current
statuses (any `DELIVERED` wins, then any `SENT`, then `FAILED` only if
every delivery is terminal) -- but never touches a notification already
`READ`, `ACKNOWLEDGED`, or `CANCELLED`, since those are outcomes a
recipient or caller actively chose, not something a late-arriving
delivery attempt gets to silently revise.

---

## Layout

| Path | What lives there |
| --- | --- |
| [`app/routing/`](app/routing/) | Pure preference-allow and quiet-hours checks (the one genuine gap in `shared_core`'s coverage) |
| [`app/rendering/`](app/rendering/) | Thin adapter onto `shared_core.notifications.renderer`/`.templates` |
| [`app/retries/`](app/retries/) | Thin adapter onto `shared_core.queue.retry`/`shared_core.notifications.retry` |
| [`app/digest/`](app/digest/) | Thin adapter onto `shared_core.notifications.digest`, plus the one genuinely new piece: rendering a built digest into a notification body |
| [`app/models/`](app/models/) | 15 tables |
| [`app/repositories/`](app/repositories/) | 15 repositories, `require_in_org` named apart from the base's unscoped `require_by_id` |
| [`app/services/`](app/services/) | 11 services -- the only layer touching infrastructure; `app/services/delivery.py` is the one place actual channel I/O happens |
| [`app/api/`](app/api/) | 9 routers, ~50 routes under `/notifications/*` -- see `app/api/__init__.py` |
| [`app/workers/`](app/workers/) | Retry sweep, digest sweep, statistics rollup, announcement expiry sweep -- all leader-elected |

---

## Running it

```bash
docker build -t aiios/notification-center-service:0.1.0 \
  -f services/notification-center-service/Dockerfile .

docker run -d --name aiios_notification_center \
  --network aiios_aiios_network -p 8026:8026 \
  -e AIIOS_DATABASE_HOST=aiios_postgres -e AIIOS_DATABASE_PORT=5432 \
  -e AIIOS_DATABASE_NAME=aiios_notification_center \
  -e AIIOS_DATABASE_USER=aiios -e AIIOS_DATABASE_PASSWORD=change-me \
  -e AIIOS_REDIS_HOST=aiios_redis -e AIIOS_REDIS_DB=28 \
  -e AIIOS_REDIS_PASSWORD=change-me \
  -e AIIOS_RABBITMQ_HOST=aiios_rabbitmq -e AIIOS_RABBITMQ_USER=aiios \
  -e AIIOS_RABBITMQ_PASSWORD=change-me -e AIIOS_RABBITMQ_VHOST=/aiios \
  aiios/notification-center-service:0.1.0
```

`GET /readiness` reports both PostgreSQL (gating) and Redis
(non-gating). Migrations: `uv run alembic upgrade head`.
`keys/jwt_public_key.pem` is the public half of
`services/authentication-service`'s signing key -- this service
verifies but never issues tokens.

Verified live against the real stack: sent a notification over HTTP
with an explicit `IN_APP` channel, read back its `DELIVERED` status and
the recorded delivery/attempt rows, subscribed a user to a topic and
broadcast to it, published an announcement, and confirmed the audit
trail and statistics dashboard reflected all of it -- all through the
actual built image, with all four leader-elected background jobs
registering and one node acquiring leadership on startup.

---

## Tests

523 tests, **98.33%** branch coverage, against real PostgreSQL, Redis,
and RabbitMQ -- including real dispatch through a `NotificationManager`
with a genuine `InAppChannel` registered (so success is tested for
real) and every other channel deliberately left unregistered (so
failure, retry, and dead-lettering are tested against a real
`ChannelUnavailableError`, not a mock).

```bash
uv run python -m pytest -q --cov=app --cov-branch --cov-fail-under=95
```

Written by four agents working in parallel, each against its own
functional slice (pure engines/enums; notification/preference/
subscription/template/channel services; delivery/announcement/
broadcast/digest/reporting services; the full HTTP API plus workers,
registrar, and telemetry) -- see "Bugs worth remembering" below for
what they found.

### The one thing the HTTP tests cannot tell you

The `app` fixture overrides only the request session, so a test's
writes roll back -- which changes **transaction lifetime**, and
anything depending on transaction lifetime is untestable there.
`AuditService.record_failure` commits in its own `session_scope` so a
refused request's audit entry survives the rollback of the request
that raised; under the SAVEPOINT that distinction vanishes and the
test would pass either way. Tested at service level against a second,
independent session opened from the real `db_session_factory`, the
same pattern every prior AI-IOS service's own conftest establishes.

### A worker's own session is not the fixture's session

Every worker opens its own session per tick -- production behaviour,
reproduced in tests via the same SAVEPOINT-bound `db_session_factory`
every other fixture shares, since it is bound to the same underlying
connection.

---

## Notes worth keeping

- **A router registered in the wrong order silently hijacked eight
  other routers' own routes.** `app/api/notifications.py`'s own
  `GET`/`DELETE /{notification_id}` (and its `/{notification_id}/...`
  lifecycle routes) match *any* single path segment under
  `/notifications/`. FastAPI/Starlette resolve routes in registration
  order, and `notifications_router` was registered first -- so
  `GET /notifications/preferences`, `/templates`, `/subscriptions`,
  `/channels`, `/announcements`, `/dead-letters`, `/statistics`,
  `/reports`, and `/audit` were all being intercepted as a UUID path
  parameter conversion attempt against the literal string
  `"preferences"` etc., failing with 400 before ever reaching their own
  intended router. Caught by nearly every list/read test in three of
  the API test files. Fixed by registering `notifications_router`
  *last* -- every other router's own literal sub-paths are never a real
  notification id, so trying them first is always correct.
- **A template update versioned itself on every edit, even ones that
  changed nothing about the content.** `TemplateService.update()`
  detects a content change by comparing each of `subject_template`/
  `body_template`/`format` against the stored value -- but the route
  forwards every field from `TemplateUpdateRequest`, set or not,
  as `None` when the caller didn't send it. Without an `is not None`
  guard, `None != "<the stored body>"` read as "the body changed",
  so updating only a template's `name` still wrote a spurious version
  history row and bumped `current_version`. Caught by a test that
  edited only the name and asserted no new version appeared.
- **Caller-supplied invalid Jinja2 syntax surfaced as an unhandled 500.**
  `shared_core.notifications.exceptions.TemplateRenderError` is a
  correct `500` for a *previously-valid, stored* template that fails at
  render time -- this platform's own fault, not the caller's. But
  `TemplateService.create()`/`.update()` also used it for syntax a
  caller had just supplied and nothing had rendered yet, which is a
  client mistake, not an internal failure. Now caught and re-raised as
  `ValidationError` (`400`).
- **A per-recipient notification's `created_by` column doesn't accept
  a broadcast's own `initiated_by`.** `BroadcastService.broadcast()`
  originally forwarded `initiated_by` (a loose identifier -- a user id,
  or potentially `"admin"`/a system name) straight into
  `NotificationService.create()`'s `actor_id`, which does `UUID(actor_id)`
  for the `created_by` column. A non-UUID initiator crashed every
  broadcast that used one. `initiated_by` now stays only on the
  `NotificationBroadcast` row itself; per-recipient notifications carry
  no `created_by` from a broadcast fan-out. Found independently by three
  of the four parallel test-writing agents (each hit it via the
  provided smoke test before writing anything of their own), fixed
  once, synced identically across every worktree.
- **`app/telemetry/tracing.py` was written correct from the start**,
  deliberately, after Prompt 053's identical file was found the same
  overall session to be silently dropping every span attribute
  (`start_span`'s signature is `start_span(tracer, name, *,
  span_type=None, **attributes)` -- no parameter is actually named
  `attributes`, so passing one as a literal keyword smuggles the whole
  dict into that catch-all under one bad key instead of spreading it).
  This service's own copy unpacks via `**{...}` at every call site and
  was confirmed correct by a real in-memory OTel exporter test, not
  just by not crashing.

---

## What's deliberately out of scope

Per docs/055's own "DO NOT IMPLEMENT": no external marketing platforms,
CRM messaging, marketing campaign management, or customer email
automation. Resolving audience targeting (roles/teams/regions/
environments) down to concrete recipient user ids is
`services/rbac-service`/`services/organization-service`'s own directory
data -- a caller wanting audience-based broadcast targeting resolves it
to an explicit user-id list or a subscription topic before calling this
service, rather than this service re-implementing another platform
service's own membership resolution.
