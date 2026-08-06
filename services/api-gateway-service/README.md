# AI-IOS Enterprise API Gateway Service

Prompt 056. The single entry point for every backend service: routing,
load balancing, authentication/authorization, rate limiting, quotas,
circuit breaking, request/response transformation, a REST management
API, a GraphQL query surface, and a WebSocket live event stream.

Runs on port **8027** against database **`aiios_api_gateway`** and
Redis **db 29**.

---

## What this service is

Every other AI-IOS service owns one business domain and exposes its own
HTTP API directly. This service sits in front of all of them: external
traffic hits `services/api-gateway-service`, which resolves a route,
authenticates and authorizes the caller, enforces rate limits/quotas,
load-balances across a backend's own registered instances, and forwards
the request -- logging both sides for statistics, reporting, and audit.

It is a **distinct service from `services/gateway/`**, Prompt 011's own
bootstrap stub (its own README says "no business or routing logic yet").
That stub was left untouched; this is Prompt 056's own, separately
registered service.

### Reused frameworks vs genuine gaps

Per this prompt's own "use every previously implemented platform
framework, do not redesign the platform" instruction, a dedicated
research pass across the existing codebase (see `AI_MEMORY.md`'s own
Prompt 056 entry for the exact source citations) found:

- **Reused directly:** `shared_core.security.jwt` (verification, never
  issuing -- this service holds no private key), `shared_core.security.rbac`
  /`.authorization` (local RBAC/ABAC against a caller's own decoded JWT
  claims -- see below), `shared_core.security.apikey` (generate/hash/
  rotate/revoke/check, this service supplies the durable persistence),
  `shared_core.cache.ratelimit`/`shared_core.security.ratelimit`
  (fixed-window and sliding-window limiters), `shared_core.connectors
  .retry.CircuitBreaker` (the 3-state breaker), `shared_core.monitoring
  .checks.check_http_reachable` (the health probe).
- **Genuine gaps, built new:** load balancing
  ([`app/loadbalancing/engine.py`](app/loadbalancing/engine.py) -- no
  primitive exists anywhere in `shared_core`), a real service-discovery
  registry (`shared_core.monitoring.services.ServiceRegistry` is a
  passive last-reported-health tracker with no host/port storage --
  this service's own `app/services/service.py` is the real thing), a
  pooled outbound HTTP client (built directly on `httpx.AsyncClient`,
  since no `shared_core.http` module exists), and request/response
  transformation (`app/transform/engine.py`).

### Local RBAC, not a live cross-service call

Every prior AI-IOS service asked to integrate the RBAC/policy-engine
prompts chose local, self-contained enforcement against a caller's own
JWT claims over a live per-request HTTP call to `services/rbac-service`
/`services/policy-engine-service` (confirmed directly in
`secrets-management-service`, `project-service`, and
`organization-service`'s own source comments, none of which build such
a client). This service follows the same precedent in
[`app/services/auth.py`](app/services/auth.py) -- no live call to
either service is made or introduced here.

### The proxy never parses the body it forwards

[`app/services/proxy.py`](app/services/proxy.py)'s `ProxyService` is
the one place actual outbound HTTP happens. Header and URL-rewrite
transformation rules apply on the live path; `BODY`-kind rules are
real, tested, and directly callable
(`TransformationService.apply_request`/`.apply_response`), but are
**not** wired into the always-streams-bytes proxy path -- a reverse
proxy must stay protocol-agnostic, and guessing at an opaque payload's
shape to apply a `BODY` rule would silently corrupt every request that
isn't JSON. A documented scope boundary, not an omission.

### GraphQL is single-schema today, not federation

[`app/graphql/schema.py`](app/graphql/schema.py) exposes gateway-level
queries (`services`, `routes`, `statistics`) against this service's own
data. No backend service registered with this gateway currently exposes
its own GraphQL schema, so there is nothing yet to federate -- extending
this into an Apollo-Federation-style aggregator is a real, separate
feature for whenever a backend speaks GraphQL, stated here rather than
silently unfulfilled.

### The WebSocket hub is per-organization, mirroring `dashboard-service`

[`app/websocket/hub.py`](app/websocket/hub.py)'s `GatewayHub`
structurally mirrors `dashboard-service`'s own `DashboardHub` (this
monorepo's established real-time precedent) -- bounded per-subscriber
queues, drop-the-slow-subscriber, heartbeat-on-idle -- keyed by
`organization_id` instead of a dashboard id, and per-process only (a
multi-replica deployment needs a shared broadcaster this class does not
implement).

### Circuit breakers are shared across every request and the health sweep

`HealthMonitorService` cannot be a request-scoped-yet-stateful
singleton and also safely hold a session open indefinitely, so its
circuit-breaker state lives in one process-wide `dict[str, CircuitBreaker]`
(`app.state.circuit_breakers`) threaded into every request-scoped
instance (`app/api/deps.py`) *and* into the health-probe sweep worker
(`app/workers/health_probe_sweep.py`) -- a breaker tripped by one live
request is a breaker the very next sweep tick already sees as open,
and vice versa.

---

## Layout

| Path | What lives there |
| --- | --- |
| [`app/routing/`](app/routing/) | Pure route matching/selection (static/dynamic/path/host/header/method/version/weighted/conditional/fallback) |
| [`app/loadbalancing/`](app/loadbalancing/) | Round-robin, least-connections, weighted, health-aware, sticky-session -- a genuine gap, built new |
| [`app/ratelimiting/`](app/ratelimiting/) | Thin adapter onto `shared_core.cache.ratelimit`/`.security.ratelimit`, plus quota period-bound math |
| [`app/health/`](app/health/) | Thin adapter onto `shared_core.monitoring.checks`/`.connectors.retry` |
| [`app/transform/`](app/transform/) | Header/URL-rewrite/body transformation, error-body normalization |
| [`app/models/`](app/models/) | 15 tables |
| [`app/repositories/`](app/repositories/) | 15 repositories, `require_in_org` named apart from the base's unscoped `require_by_id` |
| [`app/services/`](app/services/) | 12 services -- `app/services/proxy.py` is the one place actual outbound HTTP happens |
| [`app/api/`](app/api/) | 11 management routers under `/gateway/*` plus `/health`/`/liveness`/`/readiness`, a GraphQL mount, a WebSocket route, and the reverse-proxy catch-all (registered dead last -- see below) |
| [`app/graphql/`](app/graphql/) | The `strawberry-graphql` schema |
| [`app/websocket/`](app/websocket/) | `GatewayHub` -- the live event-stream fan-out |
| [`app/workers/`](app/workers/) | Health probe sweep, statistics rollup, quota reset sweep -- all leader-elected |

### The reverse-proxy catch-all is mounted dead last

`app/api/proxy.py`'s route matches *every* path and method
(`/{full_path:path}`). Mirroring notification-center-service's own
hard-learned router-ordering lesson, `app/core/factory.py` registers
every management router, the GraphQL mount, and the WebSocket route
first -- if the catch-all were registered before them, it would swallow
`/health`, every `/gateway/*` route, and `/docs` before any of them was
ever tried.

---

## Running it

```bash
docker build -t aiios/api-gateway-service:0.1.0 \
  -f services/api-gateway-service/Dockerfile .

docker run -d --name aiios_api_gateway \
  --network aiios_aiios_network -p 8027:8027 \
  -e AIIOS_DATABASE_HOST=aiios_postgres -e AIIOS_DATABASE_PORT=5432 \
  -e AIIOS_DATABASE_NAME=aiios_api_gateway \
  -e AIIOS_DATABASE_USER=aiios -e AIIOS_DATABASE_PASSWORD=change-me \
  -e AIIOS_REDIS_HOST=aiios_redis -e AIIOS_REDIS_DB=29 \
  -e AIIOS_REDIS_PASSWORD=change-me \
  -e AIIOS_RABBITMQ_HOST=aiios_rabbitmq -e AIIOS_RABBITMQ_USER=aiios \
  -e AIIOS_RABBITMQ_PASSWORD=change-me -e AIIOS_RABBITMQ_VHOST=/aiios \
  aiios/api-gateway-service:0.1.0
```

`GET /readiness` reports both PostgreSQL (gating) and Redis
(non-gating). Migrations: `uv run alembic upgrade head`.
`keys/jwt_public_key.pem` is the public half of
`services/authentication-service`'s signing key -- this service
verifies but never issues tokens.

Verified live against the real stack, through the actual built image:
registered a backend service and a route over HTTP with a real signed
JWT, proxied a real request through `/e2e/health` across the actual
Docker network to the gateway's own `/health` endpoint and got the real
backend's response back, confirmed the audit trail recorded both admin
actions, queried the GraphQL endpoint, and confirmed `/gateway/health`
reflected a real probe the leader-elected health-probe-sweep worker had
already run on its own, unprompted, inside the running container.

---

## Tests

767 tests, **99.55%** branch coverage, against real PostgreSQL, Redis,
and RabbitMQ -- including a real ASGI-mounted Starlette app standing in
for an external backend (so proxy round trips are genuine, complete
HTTP request/response cycles, not mocked) and real outbound probes
against already-running containers (RabbitMQ's management UI,
OpenSearch) for health-check tests, since `shared_core.monitoring.checks
.check_http_reachable` builds its own internal client that cannot be
pointed at a test double.

```bash
uv run python -m pytest -q --cov=app --cov-branch --cov-fail-under=95
```

Written by six agents working in parallel, each against its own
functional slice (pure engines/enums; service-registry/version/route/
client/apikey services; rate-limit/quota/transformation/health
services; the proxy and auth core; the reporting service plus the REST
management API; GraphQL/WebSocket/workers/telemetry) -- see "Bugs worth
remembering" below for what they found.

### The one thing the HTTP tests cannot tell you

The `app` fixture overrides only the request session, so a test's
writes roll back -- which changes **transaction lifetime**, and
anything depending on transaction lifetime is untestable there. This
service has no `record_failure`-style independent-commit path the way
notification-center-service's `AuditService` does; `AuditService.record`
here always runs inside the caller's own transaction.

### Health probing cannot be pointed at a test double

`shared_core.monitoring.checks.check_http_reachable` builds its own
`httpx.AsyncClient` internally -- unlike the proxy path, it cannot be
routed through an ASGI-mounted fake backend. Every health/circuit-breaker
test that needs a genuinely reachable target points at an
already-running container from the standing docker-compose stack
(RabbitMQ's management UI, OpenSearch) instead, and a genuinely
unreachable one at a real loopback port nothing listens on.

---

## Notes worth keeping

- **Every proxied request silently dropped its own query string.**
  `ProxyService.proxy()` accepted `query_string` as a parameter and
  stored it on the request log, but `_forward()` built the upstream
  target URL from the resolved path alone and never appended it --
  `GET /search?q=foo` proxied as `GET /search` on every single call.
  Fixed by threading `query_string` through `_forward()` and appending
  it to `target_url` when non-empty. Caught by a dedicated regression
  test proxying a real query string against the ASGI-mounted fake
  backend and asserting the echoed request actually carried it.
- **`VersionService.deprecate()` had no tenant isolation.** It called
  the base repository's unscoped `require_by_id(version_id)` instead of
  a tenant-scoped lookup, so any organization could deprecate any other
  organization's API version by id. Found independently by two of the
  six parallel agents. Fixed by adding `ApiVersionRepository
  .require_in_org()` and switching `deprecate()` to use it.
- **`ApiVersion.version` collided with the base entity's own
  optimistic-locking column.** `shared_core.base.BaseEntityMixin` gives
  every entity a `version: int` column, incremented on every update;
  this model declared its own `version: Mapped[str]` for the domain
  concept ("v1", "2024-01-01") under the exact same name, silently
  shadowing the inherited column. `BaseRepository.update()`'s
  `increment_version()` (`entity.version += 1`) would `TypeError` the
  moment any version row's optimistic lock was ever bumped -- and the
  live database, autogenerated from the buggy model, was missing the
  standard integer `version` column entirely (the only one of 15 tables
  missing it). Found independently by two agents. Fixed by renaming the
  domain field to `version_label` across the model, repository,
  service, and migration; the public API contract is unchanged
  (`VersionResponse.version` reads via `validation_alias="version_label"`,
  so JSON responses still say `"version"`).
- **The first-ever probe of a new, unhealthy instance crashed.**
  `HealthMonitorService.probe()` incremented `consecutive_failures` on
  a freshly constructed (not yet flushed) `ApiServiceHealth` row --
  before the column's own default had ever applied, its value was
  `None`, and `None += 1` raised `TypeError`. Fixed by initializing
  `consecutive_failures=0` explicitly at construction. Caught before
  any test-writing agent even started, by this service's own
  hand-written smoke test.
- **Two `.value`-on-a-plain-string bugs in `app/api/analytics.py`.**
  `download_report`'s filename and `generate_report`'s audit-success
  flag both called `.value` on an enum column freshly read back from
  the database -- which round-trips as a plain `str` (this service's
  own `app/models/enums.py` docstring explicitly warns about exactly
  this class of bug, and calls for the normaliser to be invoked on the
  *column*, never assumed on the record). Every `GET
  /gateway/reports/{id}/download` call raised a 500. Fixed by using
  `!s`/`str()` instead of `.value`, matching the already-correct
  pattern two lines away in the same file.
- **`app/telemetry/tracing.py` was written correct from the start**,
  using `**{...}` unpacking at every `start_span` call site, per the
  now-established repo-wide lesson (`start_span`'s signature has no
  parameter actually named `attributes` -- passing one as a literal
  keyword silently drops it). Confirmed correct by tests asserting on
  real span attributes via an in-memory OTel exporter, not just by not
  crashing.

---

## What's deliberately out of scope

Per docs/056's own scope boundaries: no OAuth2/OIDC concrete
implementation (`shared_core.security.providers.AuthenticationProvider`
is a structural `Protocol` stub only -- JWT and API-key authentication
are the two concrete methods this service implements). No live
cross-service call to `rbac-service`/`policy-engine-service` (see
above). No GraphQL federation across backend services (see above). No
body-transformation on the live proxy path (see above). No shared,
cross-replica WebSocket broadcaster -- a subscriber only receives
events published on the replica that accepted its connection.
