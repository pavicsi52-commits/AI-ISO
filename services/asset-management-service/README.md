# Asset Management Service

Enterprise asset governance for AI-IOS
([`docs/038_Enterprise_Asset_Management_Service.md`](../../docs/038_Enterprise_Asset_Management_Service.md)):
operational lifecycle, ownership, warranty, contracts, maintenance,
firmware/software, compliance, risk, cost, health, and dependency
governance for assets `services/inventory-service` has already
identified. Per docs/038's own framing: "Inventory identifies assets.
Asset Management manages assets." The ninth AI-IOS microservice built
on `packages/shared-core`, following `services/authentication-service`,
`services/user-management-service`, `services/rbac-service`,
`services/organization-service`, `services/project-service`,
`services/secrets-management-service`, `services/inventory-service`,
and `services/discovery-service`.

## Architecture

Standard service structure per
[`docs/008_Backend_Master_Architecture.md.txt`](../../docs/008_Backend_Master_Architecture.md.txt).
Every domain-specific directory docs/038's own DIRECTORY STRUCTURE
names (`ownership/`, `assignments/`, `maintenance/`, `contracts/`,
`warranty/`, `compliance/`, `risk/`, `costs/`, `lifecycle/`,
`firmware/`, `software/`, `health/`, `analytics/`, `reports/`, …) is
present but empty — the same "aspirational skeleton, real code goes
flat" precedent confirmed by direct inspection of
`services/inventory-service`'s own identically-empty `ownership/`/
`health/`/`lifecycle/`/`groups/`/`labels/`/`tags/`/… directories.
Everything actually lives in the flat `app/services/`/
`app/repositories/`/`app/models/`/`app/schemas/` layout, with two
exceptions genuinely distinct from ordinary CRUD:

- `app/dependencies/client.py` / `app/dependencies/graph_client.py` —
  `create_neo4j_driver`/`DependencyGraphClient`: a **read-only** Neo4j
  client. This service never writes graph nodes or edges — it queries
  the same `:Asset` graph `services/inventory-service`'s own
  write-capable `TopologyGraphClient` already populates, keyed by each
  `ManagedAsset.inventory_asset_id`.
- `app/assets/inventory_client.py` — `InventoryClient`: a lean REST
  client (mocked with `pytest-httpx` in tests, never a live second
  service process) that validates an `inventory_asset_id` genuinely
  exists in `services/inventory-service` before `POST /assets` agrees
  to govern it.

### Design decisions worth knowing

- **26 tables, not 25.** The prior planning pass undercounted docs/038's
  own DATABASE TABLES list by one; the actual count (verified by direct
  line-by-line reading) is 26, all created.
- **Enum provenance is documented per-enum, not assumed.** Docs/038
  gives verbatim value lists for some sections (`ASSET STATUS`,
  `CRITICALITY`, `DEPRECIATION`, `COST MANAGEMENT`, `MAINTENANCE`,
  `MAINTENANCE WINDOWS`, `COMPLIANCE`, `RISK MANAGEMENT`) but only
  names a field or a "Support"/"Track" capability list for others
  (`Warranty Status`, `Compliance Status`, `Operational Health`,
  assignment/contract/maintenance status lifecycles). Every enum in
  `app/models/enums.py` states in its own docstring whether its values
  are copied verbatim or derived, matching
  `services/inventory-service`'s own `Criticality` precedent for the
  same situation.
- **`LifecycleState` is derived from `LIFECYCLE MANAGEMENT`'s own
  action verbs, not invented.** Docs/038 names `Status` (`ASSET STATUS`,
  11 verbatim values) and `Lifecycle State` as two distinct
  `MANAGED ASSET MODEL` fields, but gives no separate noun-form value
  list for the latter — only `LIFECYCLE MANAGEMENT`'s 8 actions
  (Provision/Operate/Maintain/Upgrade/Reassign/Retire/Archive/Dispose).
  `LifecycleState` converts each action to the state it leaves an asset
  in (`PROVISIONING`/`OPERATIONAL`/`MAINTENANCE`/`UPGRADING`/
  `REASSIGNING`/`RETIRED`/`ARCHIVED`/`DISPOSED`), deliberately
  overlapping some `ManagedAssetStatus` values — the same
  Status/LifecycleState overlap `services/inventory-service`'s own
  `AssetStatus`/`LifecycleState` pair already established.
- **`OwnerRole` vs. `ContactRole` split.** Docs/038's own `OWNERSHIP`
  "Support" list names 8 roles; the two that read as reachable contacts
  rather than accountable owners ("Vendor Contact", "Escalation
  Contact") back a separate `asset_contacts` table/`ContactRole` enum,
  the other 6 back `asset_owners`/`OwnerRole` — matching the table
  split docs/038's own DATABASE TABLES list already implies.
- **Dependency analysis is a read-only consumer, never a second
  graph-writer.** Reasoned directly from docs/038's own framing rather
  than inventing a parallel asset-relationship model:
  `DependencyGraphClient` exposes `get_neighbors`/`get_dependency_graph`/
  `get_impact_analysis`/`get_blast_radius`/`get_root_cause_candidates`
  against the *same* graph `services/inventory-service` owns, the same
  "one general client, named-graph-as-filtered-view" design
  `TopologyGraphClient` established — `get_blast_radius` is `
  get_impact_analysis` at the maximum supported depth rather than a
  second Cypher query, and `get_root_cause_candidates` is
  `get_dependency_graph`'s own traversal reordered furthest-hop-first.
  `AssetDependencyAnalysis` caches the last-computed result in Postgres
  (docs/038's own "Neo4j Query Optimization"/"Caching" PERFORMANCE
  requirements) rather than re-traversing on every read.
- **Background analytics via the queue framework, not the scheduler
  framework.** Docs/038 names no `SCHEDULE MANAGEMENT` section the way
  docs/037 did for `services/discovery-service` — `app/workers/
  sweep_worker.py` is a single queue-consumed job (statistics recompute
  plus warranty/contract expiration sweep) triggered by enqueueing
  `{"organization_id": ...}`, wired to Prompt 020's own infrastructure
  only.
- **Report generation reuses every other service directly, not a
  parallel data-access layer.** `ReportService` is constructed with
  handles to `ManagedAssetService`/`CostService`/`ComplianceService`/
  `WarrantyService`/`MaintenanceService`/`RiskService`/
  `LifecycleService`/`AssetStatisticsService` and calls their existing
  public methods per report type — no report-specific query logic
  duplicates what those services already compute.
- **Route registration order is load-bearing here, unlike
  `services/inventory-service`.** `GET /assets/analytics` and
  `GET /assets/reports` share the exact one-segment shape as
  `GET /assets/{managed_asset_id}` — FastAPI/Starlette match routes by
  *shape*, not type, so `managed_asset_router` must be registered
  *after* `analytics_router`/`report_router` in `app/core/factory.py`'s
  `create_app()` or those two literal paths get shadowed by the
  catch-all and 422 on an "invalid UUID". Documented inline at the
  registration site itself.
- **No REST surface for owners/contacts/procurement/depreciation/
  firmware/software/audit/lifecycle-history.** Docs/038's own literal
  REST APIs list names 20 operations across 12 paths; every other
  sub-resource service exists for programmatic completeness (internal
  wiring — e.g. `WarrantyService.update()` denormalizes
  `ManagedAsset.warranty_status`, `FirmwareService.upsert()` records
  lifecycle history) and is exercised directly in tests, the same
  "required table, no REST list entry" shape
  `services/inventory-service`'s own category/class/tag/label/location/
  owner/contact/metadata set already established.

## Running Locally

```bash
uv sync
# Requires the repository root docker-compose stack running (Postgres,
# Redis, RabbitMQ, Neo4j) -- see the repository root README. This
# service also needs its own database created once:
#   docker exec aiios_postgres psql -U aiios -d postgres \
#     -c "CREATE DATABASE aiios_asset_management OWNER aiios;"
uv run alembic upgrade head
uv run uvicorn main:app --reload --port 8009
```

Configuration is `AIIOS_`-prefixed environment variables via
`packages/shared-core/config` (see the repository root `.env.example`
for the shared `AIIOS_DATABASE_*`/`AIIOS_REDIS_*`/`AIIOS_RABBITMQ_*`/
`AIIOS_NEO4J_*` variables) plus this service's own
`AIIOS_ASSET_MANAGEMENT_SERVICE_*` variables
(`app/config/settings.py`'s `AssetManagementServiceSettings`): `HOST`,
`PORT` (default `8009`), `CORS_ALLOWED_ORIGINS`, `JWT_PUBLIC_KEY_PATH`,
`INVENTORY_SERVICE_BASE_URL`, `HTTP_CLIENT_TIMEOUT_SECONDS`,
`DEPENDENCY_GRAPH_MAX_DEPTH`. Redis test database `11` — distinct from
every other AI-IOS service's own test database (3 authentication, 4
user-management, 5 rbac, 6 organization, 7 project, 8
secrets-management, 9 inventory, 10 discovery). Like every downstream
AI-IOS service, a missing JWT public key file is a hard startup error.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET/POST /assets`, `GET/PUT/PATCH/DELETE /assets/{id}` | Managed asset directory and lifecycle |
| `POST /assets/{id}/assign` | Assign/reassign to a principal |
| `POST /assets/{id}/transfer` | Transfer an ownership role |
| `GET/POST /assets/{id}/maintenance` | Maintenance activities |
| `GET/POST /assets/{id}/contracts` | Contracts |
| `GET/PUT /assets/{id}/warranty` | Current warranty period |
| `GET /assets/{id}/compliance` | Compliance evaluations |
| `GET /assets/{id}/risk` | Risk evaluations |
| `GET /assets/{id}/costs` | Cost history plus computed Total Cost of Ownership |
| `GET /assets/{id}/health` | Cached operational-health rollup |
| `GET /assets/{id}/dependencies` | Live Neo4j dependency/impact/blast-radius/root-cause analysis |
| `GET /assets/analytics` | Organization-wide analytics rollup |
| `GET /assets/reports` | Generate a report (8 types) |
| `GET /health` / `/readiness` / `/liveness` | Health checks (readiness includes Postgres and Neo4j connectivity) |
| `GET /metrics` | Prometheus metrics |
| `GET /docs` / `/openapi.json` | OpenAPI documentation |

Every endpoint requires valid authentication (`CurrentUserId`); tenant
isolation is enforced by every list/search/analytics query being scoped
to the `organization_id` the caller supplies, the same shape
`services/inventory-service` established.

## Testing

```bash
uv run pytest --cov=app --cov-report=term-missing
```

161 tests, 99.24% coverage, entirely against real infrastructure (the
repository root's docker-compose Postgres/Neo4j) — no mocked database,
no mocked graph. Postgres isolation between tests uses a per-test
SAVEPOINT (`join_transaction_mode="create_savepoint"`), the same
pattern every prior AI-IOS service established; Neo4j isolation instead
wipes every `:Asset` node before and after each test that touches the
graph via a disposable seed helper standing in for
`services/inventory-service`'s own writes, since this service's own
`DependencyGraphClient` is read-only and has no such write method to
reuse. `services/inventory-service` REST calls (`InventoryClient`) are
mocked with `pytest-httpx`, never a second live service process — the
same precedent `services/discovery-service`'s own `InventorySyncClient`
tests established. Dedicated coverage includes: real Neo4j multi-hop
dependency/impact/blast-radius/root-cause traversal against a hand-seeded
graph, every service's event-publication and no-publisher-configured
branches, the route-registration-order fix (`GET /assets/analytics`
resolving correctly rather than 422ing against the `{managed_asset_id}`
catch-all), the readiness endpoint's Neo4j-unreachable branch (a stub
driver swapped into `app.state` post-lifespan, since that check reads
`request.app.state.neo4j_driver` directly rather than through a
`Depends`-injected parameter), and the queue worker's handler called
directly with a fake service-factory context manager.

## Docker

Build from the **repository root** (this service is a uv workspace
member and its lockfile resolves against the whole workspace):

```bash
docker build -f services/asset-management-service/Dockerfile -t aiios/asset-management-service .
```

Built and live-health-checked against the real docker-compose network
(`aiios_aiios_network`) — `/health`/`/readiness` confirmed genuine
Postgres and Neo4j connectivity from inside the container, and an
unauthenticated `GET /assets` correctly returned `401` end-to-end
through the containerized app's real exception handlers.

## Real bugs found via testing

1. **`FirmwareService.upsert()` never recorded a "firmware_installed"
   lifecycle-history entry on an asset's *first* firmware record.**
   The final `if previous_version is not None and previous_version !=
   current_version:` guard was written to cover both the create and
   update paths, but the create path always sets `previous_version =
   None` — so the guard's own `is not None` check silently discarded
   every first-install history entry, while upgrades/rollbacks worked
   correctly. Caught by a real test asserting a `"firmware_installed"`
   entry exists after the very first `upsert()` call, which failed
   with an empty history list. Fixed by splitting the create and
   update paths into two unconditional branches — the create path
   always records `"firmware_installed"`, the update path only records
   `"firmware_upgraded"`/`"firmware_rolled_back"` when the version
   genuinely changed.

Every other mechanism — managed-asset CRUD and lifecycle-transition
event publication, assignment/ownership-transfer, warranty/contract
expiration sweeps and their event publication, maintenance
scheduling/approval/completion, compliance/risk aggregate rollups and
their event-publication thresholds, cost/TCO computation, health-rollup
threshold derivation, live Neo4j dependency analysis and caching, and
report generation across all 8 types — was verified via real
integration tests against live Postgres/Neo4j (not mocks) before this
README was written, and found no further defects.
