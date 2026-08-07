# AI-IOS Enterprise Integration Hub Service

Prompt 058. A centralized connector registry/catalog: connector
lifecycle management, credential management, data synchronization,
transformation, integration flows, event routing, health monitoring,
marketplace, analytics, reports, and audit.

Runs on port **8029** against database **`aiios_integration_hub`** and
Redis **db 31**.

---

## What this service is

Every enterprise application, cloud provider, industrial protocol, and
DevOps platform AI-IOS might ever integrate with is modeled here as a
*connector*: a catalog entry (in the marketplace), an organization-owned
instance of one (registered, configured, credentialed, tested, enabled),
and the activity around it (syncs, transformations, health probes,
routed events). Per its own OBJECTIVE section, docs/058 explicitly asks
for a **catalog and registry**, not live third-party integrations —
"Customer-specific Connectors" and literal working clients for the ~85
named built-in connectors (AWS, Kubernetes, GitHub, ServiceNow,
Prometheus, PostgreSQL, MQTT, ...) are out of scope by the prompt's own
"DO NOT IMPLEMENT" section. What *is* real and fully working: the
lifecycle state machine, the credential/secret handling, the pure
transformation and flow-execution engines, and — for any connector whose
own `config` actually declares a reachable `endpoint_url` or `host`/
`port` — genuine health/connection checks against it.

### Reused frameworks vs genuine gaps

Established by a dedicated research pass before any code was written
(see `AI_MEMORY.md`'s own Prompt 058 entry for exact source citations):

- **Reused directly:** `shared_core.security.encryption` (AES-256-GCM —
  encrypts self-managed connector credentials, i.e. OAuth2 tokens this
  service's own token exchange obtains); `shared_core.plugins.versioning`
  (`is_upgrade`/`is_downgrade`/`is_compatible`/`parse_version` — real
  semver comparison via `packaging`, used for connector upgrade/rollback
  and marketplace compatibility checks); `shared_core.monitoring.checks
  .check_http_reachable`/`.check_tcp_reachable` (connector health/
  connection probing); `shared_core.scheduler` (all four background
  workers); `shared_core.events` (the 9 domain events).
- **Genuine gaps, built new:** JSON/XML/CSV/YAML conversion plus field
  mapping/schema validation/enrichment/filtering/aggregation/
  normalization ([`app/transformations/engine.py`](app/transformations/engine.py)
  — nothing in `shared_core` converts between formats or applies these
  operations); a step-graph flow-execution engine with conditions,
  loops, parallel branches, retries, compensation, and approval gating
  ([`app/flows/engine.py`](app/flows/engine.py) — no generic workflow
  engine exists in `shared_core`); event routing/filtering/enrichment
  ([`app/routing/engine.py`](app/routing/engine.py)); a real OAuth2
  token-exchange module for the authorization-code and refresh grants
  ([`app/security/oauth.py`](app/security/oauth.py) — `shared_core
  .security.providers.AuthenticationProvider` is a bare structural
  `Protocol`, nothing implements the actual RFC 6749 handshake); a live
  credential resolver ([`app/security/credential_resolver.py`](app/security/credential_resolver.py),
  following the established `SecretCredentialResolver` precedent from
  automation-service/discovery-service/configuration-management-service).

### Two kinds of credential, two different resolution paths

`ConnectorCredential` holds either a `secret_ref` (a reference into
secrets-management-service, resolved live and never persisted in
plaintext — the same precedent every other AI-IOS service that needs a
*third-party* credential value already established) or an
`encrypted_value` (AES-256-GCM, decryptable by this service alone — for
an OAuth2 access/refresh token this service's own `app/security/oauth.py`
obtained, which has no secrets-management-service id to reference in the
first place). `CredentialService.assign()` enforces exactly one of the
two is ever given.

### The synchronization engine processes a caller-supplied batch, not a live external feed

`SyncService.run()` takes `records: list[dict]` from its own caller
rather than pulling from a real third-party data source — consistent
with the catalog/registry scope this service commits to. It's still
genuinely resumable: `ConnectorSyncJob.checkpoint["last_index"]` is
read back on every `run()` call, so calling it again with a longer (or
identical) batch picks up exactly where the last partial run stopped,
never reprocessing already-succeeded records.

### The flow engine's actions are bound to real collaborators

`FlowService._execute_step` wires `FlowEngine`'s own generic `"action"`
steps to four real operations: `"sync"` (trigger + run a sync job),
`"transform"` (apply a connector's own transformation rules),
`"route_event"` (ingest and route an event), and `"noop"`. A flow
definition can chain these with conditions, loops, parallel branches,
retries (exponential backoff via `shared_core.queue.retry
.compute_backoff_delay`), `on_error`-triggered compensation steps, and
an `APPROVAL` step that pauses a run (`status="awaiting_approval"`)
until a separate call supplies the right `context` flag to resume it.

### Routing rules live on the connector, not their own table

docs/058's own "DATABASE TABLES" section lists exactly 14 tables and
none of them is a dedicated routing-rule table — `Connector.config
["routing"]["routes"]` holds them instead, read by `app/api/events.py`
and evaluated by `app/routing/engine.py`. The same "don't invent a table
beyond the literal list" discipline `ConnectorFlow`'s own run-history
(folded into its own row, not a separate table) and `Connector.status`
lifecycle (a single `ConnectorLifecycleStatus` column, not a management
table for it) apply too.

---

## Layout

| Path | What lives there |
| --- | --- |
| [`app/transformations/`](app/transformations/) | JSON/XML/CSV/YAML conversion + 6 payload-shaping operations — a genuine gap, built new |
| [`app/flows/`](app/flows/) | The step-graph execution engine — a genuine gap, built new |
| [`app/routing/`](app/routing/) | Event filter-and-fan-out — a genuine gap, built new |
| [`app/security/`](app/security/) | `oauth.py` (token exchange) and `credential_resolver.py` (live secret resolution) |
| [`app/models/`](app/models/) | 14 tables |
| [`app/repositories/`](app/repositories/) | 14 repositories, `require_in_org` named apart from the base's unscoped `require_by_id` |
| [`app/services/`](app/services/) | 12 services |
| [`app/api/`](app/api/) | 41 routes across 8 routers under `/integrations/*` plus health |
| [`app/workers/`](app/workers/) | Health probe sweep, credential expiry sweep, flow scheduler sweep, statistics rollup — all leader-elected |

### The built-in catalog seeds itself, idempotently, on first read

`MarketplaceService.seed_builtin_catalog()` registers docs/058's own
~85-wide "BUILT-IN CONNECTORS" list (AWS, Kubernetes, GitHub,
ServiceNow, Prometheus, PostgreSQL, MQTT, and everything else named
across 12 categories) the first time `GET /integrations/marketplace` is
called for a fresh organization — not via a migration data-seed (which
would be an opinionated, hard-to-evolve choice baked into schema
history) and not requiring any separate setup step.

---

## Running it

```bash
docker build -t aiios/integration-hub-service:0.1.0 \
  -f services/integration-hub-service/Dockerfile .

docker run -d --name aiios_integration_hub \
  --network aiios_aiios_network -p 8029:8029 \
  -e AIIOS_DATABASE_HOST=aiios_postgres -e AIIOS_DATABASE_PORT=5432 \
  -e AIIOS_DATABASE_NAME=aiios_integration_hub \
  -e AIIOS_DATABASE_USER=aiios -e AIIOS_DATABASE_PASSWORD=change-me \
  -e AIIOS_REDIS_HOST=aiios_redis -e AIIOS_REDIS_DB=31 \
  -e AIIOS_REDIS_PASSWORD=change-me \
  -e AIIOS_RABBITMQ_HOST=aiios_rabbitmq -e AIIOS_RABBITMQ_USER=aiios \
  -e AIIOS_RABBITMQ_PASSWORD=change-me -e AIIOS_RABBITMQ_VHOST=/aiios \
  -e AIIOS_INTEGRATION_HUB_SERVICE_SECRET_ENCRYPTION_KEY=<base64 32-byte key> \
  aiios/integration-hub-service:0.1.0
```

`AIIOS_INTEGRATION_HUB_SERVICE_SECRET_ENCRYPTION_KEY` defaults to an
empty string for local-dev convenience only — a real deployment must
set a real key
(`shared_core.security.encryption.generate_encryption_key()`), or the
first request touching a self-managed credential raises `ValueError`.
Migrations: `uv run alembic upgrade head`. `keys/jwt_public_key.pem` is
the public half of `services/authentication-service`'s signing key —
this service verifies but never issues tokens.

Verified live against the real stack, through the actual built image:
registered a connector pointed at PostgreSQL's own real TCP port,
assigned a credential, enabled it, triggered a 3-record sync (all
succeeded), confirmed the marketplace catalog auto-seeded (76 entries),
created and ran a flow (a `route_event` step, confirmed a real event was
recorded), and — **without ever calling the manual probe endpoint** —
watched the leader-elected health-probe-sweep worker pick the connector
up and record a real `healthy` result on its own within one tick,
proactively re-confirming the same class of "does the worker actually
fire without being manually triggered" check webhook-service's own
Prompt 057 build first established as a lesson. Live-verification rows
cleaned from every table they touched (`connectors`,
`connector_credentials`, `connector_connections`, `connector_sync_jobs`,
`connector_flows`, `connector_events`, `connector_health`,
`connector_marketplace`, `connector_audit`) before the final test-suite
re-run.

---

## Tests

724 tests, **98.85%** branch coverage, against real PostgreSQL, Redis,
and RabbitMQ.

```bash
uv run python -m pytest -q --cov=app --cov-branch --cov-fail-under=95
```

Written by eleven agents across two dispatch rounds — see "Notes worth
keeping" below for why two rounds were needed.

### `check_http_reachable`/`check_tcp_reachable` cannot be pointed at a test double

Both build their own internal `httpx.AsyncClient` (the same confirmed,
repo-wide limitation `api-gateway-service`'s own test suite already
documents) — `ConnectionService`/`HealthService` tests point at
already-running containers from the standing docker-compose stack
(PostgreSQL's own port for TCP, RabbitMQ's own management UI for HTTP)
for "genuinely reachable," and a real closed loopback port for
"genuinely unreachable." `app/security/oauth.py` and `app/security
/credential_resolver.py`, by contrast, both take an *injectable*
`httpx.AsyncClient`, so their own tests point at `tests/conftest.py`'s
`fake_backend_app()` — a real ASGI Starlette app serving a fake OAuth2
token endpoint and a fake secrets-management-service `/secrets/{id}`
route — through `httpx.ASGITransport`, a genuine, complete HTTP
request/response cycle, never mocked.

---

## Notes worth keeping

- **Two of the seven test-writing agents' worktrees vanished entirely
  before writing anything, despite the tool reporting they'd
  started.** One (`app/services/connector.py` + `app/api/connectors.py`,
  the single largest remaining scope) lost its worktree with zero files
  written; a fresh agent redispatched afterward completed it cleanly
  (60 + 71 tests, 100% coverage on both files, no source bugs found).
  Five of the original seven agents' worktrees *did* survive but hit an
  account-wide session-limit mid-task, each stopping with between 1 and
  5 of its own assigned files still unwritten; every one of those
  worktrees had already committed its own partial progress before
  stopping, so nothing already written was lost, and the missing files
  (`test_oauth.py`, `test_telemetry.py`, `test_api_analytics.py`,
  `test_credential_resolver.py`, `test_api_credentials.py`) were
  finished by five freshly-dispatched agents once the account session
  limit reset. This is the same background-agent worktree-persistence
  gap `webhook-service`'s own Prompt 057 build first found — now
  confirmed to recur, and confirmed survivable by committing each
  worktree's own progress immediately upon any sign of trouble rather
  than waiting until a task is fully done.
- **`_set_path`/`_delete_path` in the transformation engine mutated a
  shared nested dict in place.** `apply_field_mapping`/`.enrichment`/
  `.normalization` each start from `dict(data)` — a shallow copy that
  protects the *top-level* keys from mutation, but shares every nested
  dict *object* by reference with the caller's original input. Setting
  or deleting a nested path that already existed silently mutated that
  original object too. Found by the pure-engines test-writing agent
  while writing a regression test for exactly this. Fixed with
  copy-on-write at every intermediate level.
- **`CredentialService.rotate()` always overwrote `expires_at`, even
  when the caller didn't pass a new one** — silently erasing a
  credential's own expiry and dropping it out of
  `list_expiring_before()`'s own sweep forever. Fixed to only update
  `expires_at` when explicitly given, mirroring how `refresh_value`
  already worked.
- **`HealthService.probe()`'s own `consecutive_failures` field never
  actually reset to zero on a successful probe** — it computed
  `connector.consecutive_failures + (0 if healthy else 1)`, which on
  success just carried the connector's prior (possibly stale) count
  forward instead of reflecting that the failure streak had just been
  broken, inconsistent with the sibling `ConnectorService
  .record_health_outcome`'s own correct `0 if succeeded else +1`
  semantics. Fixed to match.
- **`WebhookDeadLetterRepository`-class completeness gap, avoided this
  time by design**: `WebhookDeadLetterRepository` in Prompt 057 was
  fully built but completely unreachable until a coverage report caught
  it after the fact. This service's own equally-easy-to-strand
  repository method — `WebhookDeadLetterRepository`'s analog here,
  none exists, since every repository built in this service was wired
  into a service method and an API route from the same pass that
  created it, not left for a later merge to notice missing.

---

## What's deliberately out of scope

Per docs/058's own scope boundaries: no live client for any of the ~85
named built-in connectors (AWS, Kubernetes, GitHub, ServiceNow,
Prometheus, PostgreSQL, MQTT, ...) — they exist as marketplace catalog
metadata only, per the prompt's own "catalog and registry, not literal
working integrations" framing and its explicit "DO NOT IMPLEMENT:
Customer-specific Connectors" boundary. No OAuth2 *authorization* leg
(redirecting a browser to a provider's consent screen and catching the
callback) — this is a backend-only service with no UI of its own to
redirect from; only the token-endpoint legs (authorization-code
exchange, refresh) are implemented, which is everything a caller who
already has a `code` from elsewhere needs. `CREDENTIAL`/`MARKETPLACE`/
`PERFORMANCE` report kinds return empty rows rather than a bespoke
builder each, the same "not every report kind needs a real builder in
the first cut" scope decision every prior AI-IOS service's own
`ReportService` has already made.
