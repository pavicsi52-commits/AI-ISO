# AI-IOS Enterprise Webhook Service

Prompt 057. Secure incoming/outgoing webhook reception, subscriptions,
event filtering, payload transformation, HMAC signature verification,
idempotency, retry with dead-letter, replay, delivery tracking,
analytics, reports, and audit.

Runs on port **8028** against database **`aiios_webhook`** and Redis
**db 30**.

---

## What this service is

Any part of the platform can raise an internal event; any number of
outside partners can register an endpoint to receive it. This service
owns the whole lifecycle in between: matching events to subscriptions,
filtering and reshaping the payload per endpoint, signing it, delivering
it with exponential/linear backoff and a dead letter once attempts run
out, and giving back statistics, generated reports, and an append-only
audit trail. It also accepts and verifies *incoming* signed webhooks
from outside partners, the mirror image of the same delivery pipeline.

### Reused frameworks vs genuine gaps

Established by a dedicated research pass before any code was written
(see `AI_MEMORY.md`'s own Prompt 057 entry for exact source citations):

- **Reused directly:** `shared_core.events.factory`/`DomainEvent`,
  `shared_core.queue.retry.compute_backoff_delay` (exponential backoff
  with jitter, used for `RetryBackoffStrategy.EXPONENTIAL`),
  `shared_core.security.encryption` (AES-256-GCM — encrypts webhook
  signing secrets at rest; must be recoverable in plaintext to compute
  HMACs, unlike hashed API keys elsewhere in this platform).
- **Genuine gaps, built new:** linear retry backoff
  ([`app/retry/engine.py`](app/retry/engine.py) — no linear strategy
  exists in `shared_core`, only exponential), HMAC signing over both
  SHA-256 and SHA-512 through one interface with secret
  rotation/multi-secret/timestamp+nonce replay protection
  ([`app/signatures/engine.py`](app/signatures/engine.py) —
  `shared_core.security.hashing.sign` is hardcoded to SHA-256 only),
  idempotency ([`app/services/idempotency.py`](app/services/idempotency.py)
  — only a bare header-name constant exists anywhere in `shared_core`),
  and SSRF protection
  ([`app/security/url_safety.py`](app/security/url_safety.py) — no
  IP-range classification exists anywhere in `shared_core`;
  `shared_core.validators.fields.web.validate_url` only checks
  scheme/non-empty netloc).

### SSRF protection: registration-time and delivery-time, not just once

`assert_safe_url` does a genuine, non-blocking DNS resolution
(`asyncio.get_running_loop().getaddrinfo`, never the blocking
`socket.getaddrinfo` directly) and rejects any resolved address that is
private, loopback, link-local, multicast, reserved, or unspecified. It
runs both when an endpoint is *registered* and again every time a
delivery is *attempted* — a hostname that resolved to a public IP at
registration can be re-pointed at a private one later (DNS rebinding),
and only re-checking at delivery time catches that.

### Local RBAC is not applicable here

Unlike services that enforce RBAC/ABAC against a caller's own JWT
claims, this service has no cross-service authorization decision to
make — every route is scoped by `organization_id` and, where it
mutates, gated on `CurrentUserId` for audit attribution. There is no
live call to `rbac-service`/`policy-engine-service`, consistent with
every prior AI-IOS service's own precedent of local-only enforcement.

### Secret rotation with an overlap window

`SignatureService.rotate()` creates a new `ACTIVE` secret and demotes
the previous one to `ROTATING` rather than deleting it immediately — a
partner who has not yet picked up the new secret can still verify
against the old one until `overlap_hours` elapses, at which point
`SecretExpirySweepWorker` expires it. `WebhookSignature.secret_version`
is a per-endpoint monotonically increasing ordinal (see "Bugs worth
remembering" for why it isn't named `version`).

### Idempotency, incoming and outgoing

Both directions can dedupe on a caller-supplied idempotency key: an
incoming webhook with a key already seen returns the first response
without re-publishing `WebhookReceived`/`WebhookValidated`; an outgoing
delivery request with a key already seen returns the existing delivery
row rather than queueing a duplicate. `IdempotencyExpirySweepWorker`
reclaims expired reservations.

---

## Layout

| Path | What lives there |
| --- | --- |
| [`app/filters/`](app/filters/) | Pure `{field, operator, value}` rule evaluation — a genuine gap |
| [`app/subscriptions/`](app/subscriptions/) | Pure event-to-subscription scope matching (wildcard/org/project/role/user/topic/event/resource glob) |
| [`app/transformations/`](app/transformations/) | Header mapping, field removal/enrichment, template rendering, version conversion |
| [`app/signatures/`](app/signatures/) | HMAC SHA-256/SHA-512 signing, verification, timestamp+nonce replay protection |
| [`app/retry/`](app/retry/) | Exponential (delegates to `shared_core.queue.retry`) and linear (built new) backoff |
| [`app/security/`](app/security/) | `assert_safe_url` — the SSRF guard |
| [`app/models/`](app/models/) | 16 tables |
| [`app/repositories/`](app/repositories/) | 15 repositories, `require_in_org` named apart from the base's unscoped `require_by_id` |
| [`app/services/`](app/services/) | 12 services — `app/services/delivery.py`'s `DeliveryService` is the core orchestrator |
| [`app/api/`](app/api/) | 11 routers under `/webhooks/*` plus health |
| [`app/workers/`](app/workers/) | Retry sweep, replay processor, statistics rollup, idempotency expiry sweep, secret expiry sweep — all leader-elected |

### `/webhooks/dead-letters` is a separate router, not a sub-path

`app/api/deliveries.py` deliberately registers dead-letter routes on
their own `APIRouter(prefix="/webhooks/dead-letters")` rather than
nesting them under `/webhooks/deliveries/dead-letters` — that shape
would collide with `GET /webhooks/deliveries/{delivery_id}`, which
would swallow a literal `"dead-letters"` path segment as a delivery id
unless registered strictly first. The same router-ordering hazard
notification-center-service and api-gateway-service each hit once
already in this build.

---

## Running it

```bash
docker build -t aiios/webhook-service:0.1.0 \
  -f services/webhook-service/Dockerfile .

docker run -d --name aiios_webhook \
  --network aiios_aiios_network -p 8028:8028 \
  -e AIIOS_DATABASE_HOST=aiios_postgres -e AIIOS_DATABASE_PORT=5432 \
  -e AIIOS_DATABASE_NAME=aiios_webhook \
  -e AIIOS_DATABASE_USER=aiios -e AIIOS_DATABASE_PASSWORD=change-me \
  -e AIIOS_REDIS_HOST=aiios_redis -e AIIOS_REDIS_DB=30 \
  -e AIIOS_REDIS_PASSWORD=change-me \
  -e AIIOS_RABBITMQ_HOST=aiios_rabbitmq -e AIIOS_RABBITMQ_USER=aiios \
  -e AIIOS_RABBITMQ_PASSWORD=change-me -e AIIOS_RABBITMQ_VHOST=/aiios \
  -e AIIOS_WEBHOOK_SERVICE_SECRET_ENCRYPTION_KEY=<base64 32-byte key> \
  aiios/webhook-service:0.1.0
```

`AIIOS_WEBHOOK_SERVICE_SECRET_ENCRYPTION_KEY` defaults to an empty
string for local-dev convenience only — a real deployment must set a
real key (`shared_core.security.encryption.generate_encryption_key()`),
or the very first request that touches a signing secret raises
`ValueError`. Migrations: `uv run alembic upgrade head`.
`keys/jwt_public_key.pem` is the public half of
`services/authentication-service`'s signing key — this service verifies
but never issues tokens.

Verified live against the real stack, through the actual built image:
registered an endpoint pointed at a real public backend, created a
signing secret and a wildcard subscription, raised an internal event,
and — **without ever calling the manual retry endpoint** — watched the
leader-elected retry-sweep worker pick the queued delivery up on its
own next tick and mark it `delivered`, confirming the fix described
below. Also confirmed the audit trail recorded both admin actions and
that `/webhooks/dead-letters` and `/webhooks/statistics` reflect real
state. Live-verification rows cleaned from every table they touched
(`webhook_endpoints`, `webhook_signatures`, `webhook_subscriptions`,
`webhook_events`, `webhook_deliveries`, `webhook_delivery_attempts`,
`webhook_retry_queue`, `webhook_audit`) before the final test-suite
re-run.

---

## Tests

721 tests, **98.44%** branch coverage, against real PostgreSQL, Redis,
and RabbitMQ — including a real ASGI-mounted Starlette app standing in
for an external delivery target (`tests/conftest.py`'s
`fake_backend_app`, reached through `httpx.ASGITransport`), so every
delivery in the suite is a genuine, complete HTTP request/response
cycle, never mocked.

```bash
uv run python -m pytest -q --cov=app --cov-branch --cov-fail-under=95
```

Written by six agents working in parallel, each against its own
functional slice (pure engines/enums; event ingestion/idempotency;
`DeliveryService` core; CRUD services and their REST surface;
workers/telemetry; replay/reporting and their REST surface) — see "Bugs
worth remembering" below for what they, and the merge that followed,
found.

### `example.com`, not a fake hostname, as the test delivery target

`assert_safe_url` does genuine DNS resolution before any request is
attempted, so a made-up hostname like `http://backend.test` fails with
`socket.gaierror` before ever reaching the substituted transport.
`tests/conftest.py`'s `FAKE_BACKEND_URL` is `http://example.com`
instead — IANA-reserved, always publicly resolvable — while the actual
HTTP traffic still never touches the network, since `http_client`'s
*sole* transport is `ASGITransport(app=fake_backend_app())`.

### The one thing the HTTP tests cannot tell you

The `app` fixture overrides only the request session, so a test's
writes roll back — which changes **transaction lifetime**, and
`AuditService.record_failure`'s deliberate independent `session_scope`
commit (so a refused request's audit entry survives that request's own
rollback) is therefore exercised at service level against the real
`db_session_factory`, never through the `client` HTTP fixture.

---

## Notes worth keeping

- **A freshly-queued delivery was never actually attempted by
  anything.** `DeliveryService.fan_out()`/`.queue_direct()` only ever
  created a `QUEUED` delivery row; nothing in the request path or any
  worker ever called `.deliver()` for it. `RetrySweepWorker` only walks
  rows already present in `webhook_retry_queue`, and that table was
  only ever populated by `_schedule_retry()` *after* a first attempt
  had already failed — so the very first attempt had no path to ever
  happen automatically, and every event raised through the normal
  `POST /webhooks/events` → fan-out path sat `QUEUED` forever unless a
  caller manually hit `POST /webhooks/deliveries/{id}/retry`. This is
  this service's own core feature failing silently — found live,
  post-merge, running the actual built image against the real stack
  (every one of the 721 automated tests passed regardless, because
  every test that exercises delivery calls `.deliver()` itself, mirroring
  a caller that would not exist in production). Fixed by having both
  `fan_out()` and `queue_direct()` schedule a `webhook_retry_queue` entry
  (`attempt_number=0`, `next_attempt_at=now`) for every delivery they
  create, so the very next retry-sweep tick picks it up — `attempt_count`
  on the delivery itself stays `0` until that tick actually runs, so the
  existing "just queued" API-response contract is unchanged. Locked in by
  a live re-run (queue an event, deliberately never call retry, watch the
  worker deliver it on its own) plus new regression tests in
  `test_delivery_service.py` and `test_workers.py`.
- **`WebhookSignature.version` collided with the base entity's own
  optimistic-locking column.** `shared_core.base.BaseEntityMixin` gives
  every entity a `version: int` column, incremented on every update;
  this model declared its own domain rotation-ordinal under the exact
  same name, silently shadowing the inherited column at the SQLAlchemy
  declarative level — `BaseRepository.update()`'s `entity.version += 1`
  was corrupting the domain field on every unrelated update, eventually
  colliding with the `(endpoint_id, version)` unique constraint. Found
  independently by three of the six parallel agents. Fixed by renaming
  the domain field to `secret_version` across the model, repository,
  service, schema, and migration (which also restored the real
  `version` integer column that Python-level shadowing had prevented
  SQLAlchemy from ever registering for autogenerate in the first
  place). The third occurrence of this exact class of bug in this
  build (Prompt 056's `ApiVersion.version`, Prompt 057's own
  `WebhookSignature.version` and, below, `StatisticsService`'s
  `by_endpoint` grouping bug born from the same root migration issue)
  — now a fully-established, repo-wide rule: never name a domain field
  `version`.
- **A cross-tenant secret-hijack gap.** `POST`/`GET /webhooks/filters`,
  `/webhooks/transformations`, and `/webhooks/signatures` (create and
  rotate) accepted a `subscription_id`/`endpoint_id` without ever
  confirming it belonged to the caller's own `organization_id` — an
  organization could rotate another organization's endpoint's signing
  secret by guessing or enumerating its id. Found by the CRUD-services
  agent. Fixed by adding an ownership check (the already tenant-scoped
  `SubscriptionService.get`/`EndpointService.get`) as the first line of
  every affected route handler.
- **`StatisticsService.rollup()`'s `by_endpoint` breakdown was actually
  keyed by `attempt.delivery_id`.** Every window's per-endpoint traffic
  split was silently wrong — keyed by an id that happens to also be a
  UUID string, so nothing type-checked or crashed. Root cause: the
  original `WebhookDeliveryAttempt` model had no `endpoint_id` column
  at all, only `delivery_id`. Fixed by adding a denormalized
  `endpoint_id` column to `webhook_delivery_attempts` (mirroring
  `ApiResponseLog.organization_id`'s precedent from
  api-gateway-service), applied directly to the live database since it
  held zero rows at the time, and fixing the grouping loop to key by
  the new column.
- **`POST /webhooks/deliveries/{id}/retry` had no `CurrentUserId` or
  audit logging**, unlike every other mutating route in this service.
  Found by the `DeliveryService` agent, explicitly deferred as
  requiring an API signature change outside that task's own scope.
  Fixed during merge: added `CurrentUserId`/`AuditSvc` and a
  `DELIVERY_RETRIED` audit entry.
- **`WebhookDeadLetterRepository` was fully built — `require_in_org`,
  `list_for_org` — but completely unreachable from any service method
  or API route.** Found from the coverage report alone
  (`app/repositories/retry.py` sitting at 76%, missing exactly the
  dead-letter methods), not flagged by any agent. Fixed by adding
  `DeliveryService.get_dead_letter()`/`.list_dead_letters()`, a
  `DeadLetterResponse` schema, and the `dead_letters_router` described
  above.
- **`app/telemetry/tracing.py` was written correct from the start**,
  using `**{...}` unpacking at every `start_span` call site, per the
  now fully-established repo-wide lesson (`start_span` has no parameter
  actually named `attributes` — passing one as a literal keyword
  silently drops it).

### A background agent's reported work vanished with its worktree

One of the six parallel agents (replay/reporting service plus its own
REST API) reported completing its work twice — once before a
session-limit failure, once after resuming — with specific file names
and test counts. At merge time neither a worktree directory nor a git
branch existed for it anywhere. The work was genuinely unrecoverable.
Mitigated by salvaging a different agent's incidental duplicate copies
of three of the four files (written as a side effect of that agent
exercising the same services during its own testing) and hand-writing
the one file — `tests/test_api_analytics.py` — that nobody's surviving
copy had. This is a real, unresolved gap in the background-agent
worktree persistence mechanism, not specific to this service: a
reported completion is not proof a worktree survived to be merged.

---

## What's deliberately out of scope

Per docs/057's own scope boundaries: no OAuth2/OIDC for incoming
webhook authentication (HMAC signing is the one concrete method this
service implements, matching how the vast majority of real-world
webhook providers — Stripe, GitHub, etc. — actually authenticate
outgoing traffic). `ENDPOINT`/`REPLAY`/`SECURITY` report kinds return
empty rows rather than a bespoke builder each, the same "not every
report kind needs a real builder in the first cut" scope decision every
prior AI-IOS service's own `ReportService` has already made. No
cross-replica WebSocket/live event stream — this service's own
`WebhookDelivered`/`WebhookFailed`/etc. domain events are published to
RabbitMQ for any other service to subscribe to, not pushed to a
browser directly.
