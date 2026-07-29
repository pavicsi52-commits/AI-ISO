# AI-IOS Dashboard Service

Prompt 048. The dashboard platform: a drag-and-drop builder, eighteen
widget types over thirteen data sources, responsive per-breakpoint
layouts with real undo/redo, topology visualisation over Neo4j,
real-time updates on SSE and WebSocket, themes with WCAG contrast
auditing, a template library, sharing, and usage analytics.

Runs on port **8019** against database **`aiios_dashboard`** and Redis
**db 21**.

---

## What this service is

A dashboard is the thing an operator stares at during an incident. Every
design decision below follows from that: **partial output beats no
output**, and **nothing may show a viewer data they could not have
fetched themselves**.

### Widgets degrade; dashboards do not fail

One unreachable source marks its own tile `FAILED` with the reason.
Every other widget still renders and the request is still a `200`. A
dashboard that returns nothing because one of thirteen sources is down
is the wrong failure mode.

### Every widget is read with the caller's own token

`PlatformSourceClient` forwards the caller's bearer token to every
source service. This service holds no privileged credential of its own,
so RBAC stays enforced by the service that owns the data. A `403` from a
source is the correct outcome, not a bug.

That single decision shapes three others:

- **The refresh worker notifies; it never fetches.** A broadcast frame
  reaches every watcher of a dashboard at once, and those are different
  people with different rights. Pushing one credential's resolved rows
  down that channel would hand whatever it could see to everyone else.
  Frames say *that* something changed; clients re-fetch under their own
  token. The worker consequently needs no database session, no HTTP
  client, and no credentials at all.
- **A share link opens structure, not data.** A signed-in visitor
  following a link resolves widgets with their own token. An anonymous
  one gets the dashboard, its layout, and every widget marked
  `UNAUTHORIZED`. Resolving under the *sharer's* rights would silently
  hand a stranger whatever that person can see.
- **The snapshot is the one exception**, and it is safe: it is resolved
  with the connecting caller's own token and sent down that caller's own
  connection only.

### Layout history is real

Every layout save writes a **new row**. Restoring points `is_current` at
an earlier revision rather than copying it forward, so undo/redo and
"Saved Layouts" work against arrangements that still exist exactly as
they were. `Dashboard.layout_revision` and `DashboardLayout.revision`
are deliberately *not* named `version` — that name belongs to
`BaseEntityMixin`'s optimistic-lock counter, which `BaseRepository`
increments on every write. Redeclaring it has shipped as a live bug
twice in this platform.

### Two workers with opposite scaling behaviour

| Worker | Scope | Why |
| --- | --- | --- |
| `StatisticsWorker` | leader-elected, one replica | The rollup is a pure database write; N replicas computing it would be N times the load for an identical result, and two concurrent recomputes would race on the same row. |
| `RefreshWorker` | **every** replica | Subscribers live in the process that accepted their connection. An elected replica would notify only its own watchers and freeze everyone else. |

The refresh loop iterates `hub.watched_dashboards()`, not the dashboards
table, so its cost is proportional to the live audience rather than the
size of the installation.

---

## Layout

```
app/
  api/          health, dashboards, sharing, catalog (themes+templates), analytics
  clients/      PlatformSourceClient -- authenticated reads of 13 sources
  config/       settings, JWT verification key loading
  core/         application factory
  events/       7 domain events, all genuinely published
  filters/      the filter grammar, identical to reporting-service's
  layouts/      the grid engine: overlap, compaction, reflow, reconciliation
  models/       14 tables
  notifications/ best-effort delivery
  realtime/     the hub (back-pressure, heartbeats) + Redis cross-replica relay
  repositories/ 14 repositories
  schemas/      request/response shapes
  services/     dashboard, sharing, statistics, audit, theme, template,
                preferences, streaming
  telemetry/    spans for load, widget render, topology, streaming, filters
  templates/    template documents, validated for coherence
  themes/       palettes, branding, WCAG contrast maths
  topology/     Neo4j driver lifecycle + Cypher construction
  widgets/      widget definitions + the resolver
  workers/      refresh (per-replica), statistics (leader-elected), registrar
```

---

## API

Paths follow docs/048 exactly. **No `/api/v1` prefix** — the gateway
owns versioning, the convention every AI-IOS service follows.

53 operations plus one WebSocket. The ones docs/048 names:

```
GET    /dashboards                     POST   /dashboards
GET    /dashboards/{id}                PUT    /dashboards/{id}
DELETE /dashboards/{id}
GET    /dashboards/templates           POST   /dashboards/templates
GET    /dashboards/widgets             POST   /dashboards/widgets
GET    /dashboards/layouts             POST   /dashboards/layouts
POST   /dashboards/share
GET    /dashboards/statistics
```

Plus loading, layout restore, favourites, saved filters, history,
themes, sharing links, role permissions, audit, topology, presence, and
both live transports.

**Route order is load-bearing.** docs/048 specifies both
`/dashboards/{id}` and literal collections like
`/dashboards/statistics`. FastAPI matches in registration order, so the
literal-segment routers are included *before* the `{dashboard_id}` one —
otherwise `/dashboards/statistics` parses as a dashboard whose id is the
word "statistics" and 422s forever. See `app/api/__init__.py`.

### Live transports

- `GET /dashboards/{id}/stream` — Server-Sent Events. Opens with a
  snapshot, then updates and heartbeats.
- `WS /dashboards/{id}/ws?token=…` — the token is a query parameter
  because browsers cannot set headers on a WebSocket handshake. It is
  verified with the same public key as every HTTP route; an invalid one
  closes the socket with 1008.

Both read the same `Subscriber` queue, so back-pressure, heartbeats, and
slow-subscriber eviction behave identically rather than drifting apart.

---

## Running it

```bash
# Migrations run as a separate step, never baked into CMD, so a
# multi-replica rollout cannot race two containers on the same migration.
uv run alembic upgrade head
uv run uvicorn main:app --host 0.0.0.0 --port 8019 --reload
```

```bash
# Build context must be the repository root -- this service is a member
# of the root uv workspace.
docker build -f services/dashboard-service/Dockerfile -t aiios/dashboard-service .
```

---

## Tests

336 tests, **97% coverage**, all against real infrastructure.

```bash
uv run python -m pytest --cov=app --cov-report=term-missing
```

| File | Covers |
| --- | --- |
| `test_core_logic.py` | grid, filters, widget validation, WCAG maths, Cypher, frame encoding |
| `test_services.py` | every service against real Postgres, with reload-based enum checks |
| `test_api.py` | the HTTP contract through the real app lifespan |
| `test_realtime_and_workers.py` | hub, real-Redis cross-replica relay, both workers, health |
| `test_widget_resolution.py` | all eighteen shapes and every failure path |
| `test_transports.py` | a real WebSocket and the SSE route body |

Three testing decisions worth knowing:

1. **Enum normalisers are verified through a genuine reload.** A model
   built in memory holds a real enum member; a row read back from
   Postgres holds a plain `str`. Tests that never reload cannot tell the
   difference — which is exactly why four dead features shipped across
   this platform before anyone noticed. Every normaliser here is checked
   after `await db_session.refresh(...)`.
2. **Neither test client can drive an SSE endpoint.** `ASGITransport`
   and Starlette's `TestClient` both want a response body that ends, and
   an SSE stream is endless by construction — requesting one hangs the
   suite rather than testing it. The route function is called directly
   and its own generator consumed. The WebSocket, by contrast, *is*
   driven over a real socket.
3. **The scheduler and refresh loop are disabled in the suite** and
   exercised through their own `tick()`. A background tick publishing
   frames underneath a test asserting on exactly what a subscriber
   received is a flake generator.

---

## Configuration

All `AIIOS_DASHBOARD_SERVICE_`-prefixed. The ones that matter:

| Setting | Default | Why |
| --- | --- | --- |
| `MAX_ROWS_PER_WIDGET` | 5000 | A table widget pulling a million rows stalls the dashboard for everyone on it. |
| `MAX_PARALLEL_WIDGETS` | 6 | Bounds concurrent *network* fetches. Nothing here touches the database concurrently — an `AsyncSession` is not safe for that even for reads. |
| `MAX_WIDGETS_PER_DASHBOARD` | 60 | |
| `STREAM_HEARTBEAT_SECONDS` | 20 | An idle socket is indistinguishable from a dead one, and proxies close silent connections without telling either end. |
| `STREAM_MAX_SUBSCRIBERS` | 500 | Refusing a connection beats accepting one the process cannot serve. |
| `REFRESH_POLL_SECONDS` | 15 | Per-replica; see the worker table above. |
| `TOPOLOGY_MAX_DEPTH` | 4 | Graph traversal grows exponentially; an unbounded blast-radius query on a large estate is an outage, not a visualisation. |
| `TOPOLOGY_MAX_NODES` | 500 | A graph that hits the ceiling is returned flagged `truncated`. |
| `STATISTICS_ROLLUP_SECONDS` | 900 | Leader-elected. |
| `SHARE_LINK_TTL_SECONDS` | 604800 | Enforced on read, not merely stored. |

---

## Operational notes

- **Readiness reports the graph but does not gate on it.** Topology is
  one widget type among eighteen; refusing all traffic because Neo4j is
  down would take out every dashboard that never touches it.
- **Presence is replica-scoped**, and the response says so. Each process
  knows only its own connections; relaying presence would let replicas
  overwrite each other with partial lists. A shared presence view needs
  the broadcaster to aggregate — a deliberate future step rather than
  something faked here.
- **Cross-replica relay is fire-and-forget** over one Redis channel. A
  dashboard frame is worth delivering *now* or not at all: a widget
  value arriving thirty seconds late after a broker replay is worse than
  one the client re-fetches on its next tick. A relayed frame is
  published with `relay=False` so two replicas cannot bounce it forever.
- **Contrast shortfalls are reported, not rejected.** A brand colour is
  sometimes fixed by forces outside engineering, and a visible, specific
  shortfall is more useful than a refusal that gets worked around by
  turning the check off. `GET /dashboards/themes/{id}/accessibility`
  names each failing pair and its ratio.
- **Audit writes are best-effort and never fail the audited action.**
  Refusing to render a dashboard because an audit insert hit a deadlock
  turns a bookkeeping problem into an operational one. Services with a
  regulatory retention duty — `secrets-management`, `compliance` — make
  the opposite choice deliberately.
- **Every Cypher value is parameterised.** Node ids arrive from
  user-authored widget definitions. Depth cannot be parameterised in a
  Cypher range literal, so it is validated as a bounded integer before
  interpolation — the single place a value is formatted into query text,
  and the reason that validation is not optional.

### Local test gotchas

- Test conftests use `127.0.0.1`, never `localhost`. On Windows
  `localhost` resolves to `::1` first and Docker Desktop's IPv6
  forwarding hangs rather than refusing, so every connection burns its
  full timeout instead of falling back.
- `MSYS_NO_PATHCONV=1` is mandatory for any `docker run` argument
  starting with `/`, or Git Bash rewrites it into a Windows path.
