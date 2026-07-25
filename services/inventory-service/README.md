# Inventory Service

Centralized, authoritative inventory/CMDB for AI-IOS
([`docs/036_Enterprise_Inventory_Service.md`](../../docs/036_Enterprise_Inventory_Service.md)):
every discovered asset across hybrid, cloud, edge, industrial, and
Kubernetes environments SHALL be represented here, with Neo4j-backed
relationship and topology tracking. The seventh AI-IOS microservice
built on `packages/shared-core`, alongside
`services/authentication-service`, `services/user-management-service`,
`services/rbac-service`, `services/organization-service`,
`services/project-service`, and `services/secrets-management-service`
— and the first to talk to Neo4j at all.

## Architecture

Standard service structure per
[`docs/008_Backend_Master_Architecture.md.txt`](../../docs/008_Backend_Master_Architecture.md.txt).
A few sub-packages specific to this service's domain:

- `app/topology/client.py` / `app/topology/graph.py` —
  `create_neo4j_driver`/`TopologyGraphClient`: the official `neo4j`
  async driver (no `shared_core` wrapper exists yet — confirmed via
  reuse research; `shared_core` only provides `Neo4jSettings` config
  plumbing) wrapped in general-purpose node/edge maintenance plus
  neighbor/dependency/impact traversal.
- `app/services/topology.py` — `TopologyService`: wraps
  `TopologyGraphClient` with a 5-minute Postgres-backed cache
  (`asset_topology_cache`) so repeated traversals for the same asset
  don't round-trip to Neo4j every time.
- `app/parsers/` — CSV/JSON/YAML parsers copied near-verbatim from
  `services/project-service`; Excel parser copied near-verbatim from
  `services/user-management-service`; `pdf_writer.py`/`zip_archive.py`
  extended to cover the two additional formats docs/036 lists that
  docs/034 never needed (Excel import+export, PDF export-only summary).
- `app/telemetry/tracing.py` — inventory CRUD, topology update,
  relationship query, import, export, synchronization, and search
  spans.

### Design decisions worth knowing

- **Postgres stays authoritative; Neo4j is a best-effort mirror.**
  `asset_relationships` is the single source of truth for relationship
  data — every create/delete is synchronously mirrored into Neo4j by
  the service layer (`AssetRelationshipService`/`AssetService`), but a
  Neo4j failure never blocks the relational write it's mirroring, and
  there is no distributed-transaction coordination between the two
  stores. This deliberately avoids treating Neo4j as a second source
  of truth requiring two-phase commit.
- **One general-purpose graph client, not seven bespoke queries.**
  Docs/036 names seven "graph" concepts (Dependency Graph, Network
  Graph, Application Graph, Infrastructure Graph, Industrial Topology,
  Cloud Topology, Kubernetes Topology) — rather than one Cypher query
  per name, `TopologyGraphClient` exposes node/edge CRUD plus
  neighbor/dependency/impact traversal, and the different "named
  graphs" are all `AssetType`-filtered views resolved at the service
  layer, not distinct graph-layer queries.
- **Three-level classification hierarchy.** `AssetCategory` (broadest,
  e.g. "Compute") → `AssetClass` (nested under a category, e.g.
  "Server") → `AssetType` (the asset's own fixed 44-value enum column).
  `AssetTypeDefinition` (the `asset_types` catalog table) is pure
  reference data — a display name/icon/category, never a foreign-key
  target for `Asset.asset_type` itself — so asset creation is never
  blocked on a catalog entry existing first.
- **Static-vs-dynamic group membership, stored differently.**
  Static/location/application/environment/custom groups persist
  membership as a JSON `member_asset_ids` list (reusing
  `services/secrets-management-service`'s `credential_sets.secret_ids`
  precedent); dynamic/rule-based groups instead store a `rule` JSON
  filter (`{field, operator, value}`, `eq`/`ne` only — a documented
  scope limit, not a silent gap) evaluated live against the current
  asset list on every read.
- **Schema/value split for custom attributes.** `AssetCustomField`
  (definition: name, type, validation rule, required) vs.
  `AssetAttribute` (per-asset typed value, validated at write time by
  `_validate_typed_value()` against `STRING`/`INTEGER`/`FLOAT`/
  `BOOLEAN`/`DATE`/`JSON`).
- **`shared_core.enums.job_status.JobStatus` reuse.** `AssetImportJob`/
  `AssetExportJob` reuse this shared 13-value enum rather than a
  service-local status enum, matching
  `services/project-service`'s own `ProjectImportJob`/`ProjectExportJob`
  precedent exactly.
- **No REST surface for category/class/type/tag/label/location/owner/
  contact/metadata/custom-field/attribute/discovery-link.** Docs/036's
  own literal REST list names only nine endpoints (assets, import,
  export, search, groups, topology, relationships, statistics,
  analytics) — every other sub-resource service exists for
  programmatic completeness and is exercised directly in tests, the
  same "required table, no REST list entry" shape
  `services/secrets-management-service`'s own `TokenService`
  established.

## Running Locally

```bash
uv sync
# Requires the repository root docker-compose stack running (Postgres,
# Redis, RabbitMQ, Neo4j, MinIO) -- see the repository root README.
# This service also needs its own database created once:
#   docker exec aiios_postgres psql -U aiios -d postgres \
#     -c "CREATE DATABASE aiios_inventory OWNER aiios;"
uv run alembic upgrade head
uv run uvicorn main:app --reload --port 8007
```

Configuration is `AIIOS_`-prefixed environment variables via
`packages/shared-core/config` (see the repository root `.env.example`
for the shared `AIIOS_DATABASE_*`/`AIIOS_REDIS_*`/`AIIOS_RABBITMQ_*`/
`AIIOS_NEO4J_*`/`AIIOS_MINIO_*` variables) plus this service's own
`AIIOS_INVENTORY_SERVICE_*` variables (`app/config/settings.py`'s
`InventoryServiceSettings`): `HOST`, `PORT`, `CORS_ALLOWED_ORIGINS`,
`JWT_PUBLIC_KEY_PATH`, `IMPORT_EXPORT_BUCKET`,
`TOPOLOGY_SYNC_INTERVAL_SECONDS`. Like every downstream AI-IOS service,
a missing JWT public key file is a hard startup error.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET/POST /inventory/assets`, `GET/PUT/PATCH/DELETE /inventory/assets/{id}` | Asset directory and lifecycle |
| `GET/POST /inventory/relationships`, `DELETE /inventory/relationships/{id}` | Relationship edges (dual-written to Neo4j) |
| `GET /inventory/topology` | Neighbor/dependency-graph/impact-analysis traversal |
| `GET/POST /inventory/groups`, `GET /inventory/groups/{id}/members` | Asset groups (static and dynamic/rule-based) |
| `POST /inventory/import`, `GET /inventory/import/{id}`, `POST /inventory/import/{id}/rollback` | Bulk import (CSV/Excel/JSON/YAML/ZIP) |
| `POST /inventory/export`, `GET /inventory/export/{id}` | Bulk export (CSV/Excel/JSON/YAML/PDF/ZIP) |
| `GET /inventory/search` | Full-text search, filtering, sorting, pagination |
| `GET /inventory/statistics` / `/inventory/analytics` | Current-state rollup / rollup plus discovery + growth trends |
| `GET /health` / `/readiness` / `/liveness` | Health checks (readiness includes Postgres, Redis, and Neo4j connectivity) |
| `GET /metrics` | Prometheus metrics |
| `GET /docs` / `/openapi.json` | OpenAPI documentation |

Every endpoint requires valid authentication (`CurrentUserId`); none of
this service's mutations reference a pre-existing organization
membership to authorize against (unlike
`services/project-service`'s role-gated sub-resources), so every
authenticated caller may act within the `organization_id` they supply
— tenant isolation is enforced by every list/search/statistics query
being scoped to that `organization_id`, never a platform-wide view.

## Testing

```bash
uv run pytest --cov=app --cov-report=term-missing
```

197 tests, 98.42% coverage, entirely against real infrastructure (the
repository root's docker-compose Postgres/Redis/RabbitMQ/Neo4j/MinIO)
— no mocked database, no mocked graph. Postgres isolation between
tests uses a per-test SAVEPOINT (`join_transaction_mode=
"create_savepoint"` — see `tests/conftest.py`), the same pattern every
prior AI-IOS service established; Neo4j isolation instead wipes every
`:Asset` node before and after each test that touches the graph, since
Neo4j has no equivalent rollback mechanism. Dedicated coverage
includes: duplicate-identifier rejection (hostname/serial/MAC),
status/health/lifecycle transition history and event publication, real
Neo4j node/edge upsert-delete and multi-hop dependency/impact
traversal (depth-bounded, cross-checked by hand against a known
topology), Postgres-cache-hit verification (deleting an edge in Neo4j
directly and confirming a cached read still returns it), static vs.
dynamic/rule-based group membership resolution, every import/export
format round-trip including ZIP's dual-purpose bundling behavior, and
the same commit-visibility worker regression tests
`services/project-service`'s own `test_worker_regression.py`
established (`create_job()` must commit before the queue message is
published; a worker's own commit must be visible to an independent
connection).

## Docker

Build from the **repository root** (this service is a uv workspace
member and its lockfile resolves against the whole workspace):

```bash
docker build -f services/inventory-service/Dockerfile -t aiios/inventory-service .
```

Built and health-checked live against the real docker-compose network
(`aiios_aiios_network`) — `docker ps` reports `(healthy)`, and
`/health`/`/readiness` confirm genuine Postgres/Redis/Neo4j
connectivity from inside the container.

## Real bugs found via live smoke-testing

Per this repository's "start the real service and exercise it" testing
discipline, found *before* the automated test suite was written, then
covered by dedicated regression tests:

1. **`AssetRelationshipService.delete()` crashed with
   `AttributeError: 'str' object has no attribute 'value'`.** The same
   SQLAlchemy weak-identity-map/enum-column bug first found in
   `services/secrets-management-service`'s `SecretService.update()`
   (every AI-IOS enum column is declared `String`, never
   `sqlalchemy.Enum`, so a row reloaded after its earlier in-memory
   instance was garbage-collected returns the raw string, not a
   reconstituted enum member) — reproduced live for the first time
   *outside* that service, in `app/topology/graph.py::
   _relationship_label()`'s `relationship_type.value.upper()` call.
   Confirmed deterministically: create a relationship in one request,
   delete it in a second, and the second request's freshly-reloaded
   `AssetRelationship.relationship_type` was already a bare string by
   the time `_relationship_label()` ran. Fixed via
   `str(relationship_type).upper()` instead of `.value.upper()` —
   identical result either way, since `RelationshipType` is a
   `StrEnum`. Proactively grepped for every other `.value` access in
   the codebase afterward and found one more live occurrence (below);
   every other hit was a function parameter or Pydantic-validated
   request field, never a freshly-reloaded ORM attribute, so safe.
2. **`AssetAttributeService._validate_typed_value()` had the identical
   latent bug**, on `field_type.value` in its error-message
   f-string — `field_type` there is `field.field_type`, freshly loaded
   via `require_by_id()` a call earlier. Never triggered in practice
   during smoke testing (no invalid-value request happened to land
   after the row's in-memory instance had already been collected), but
   fixed proactively for the same reason, using `field_type!s`
   (`str()` formatting) in place of `.value`.
3. **`AssetService.create()` never actually enforced "Prevent duplicate
   identifiers"** despite docs/036's own SECURITY section requiring it
   and `AssetRepository.get_by_hostname`/`get_by_serial_number`/
   `get_by_mac_address` already existing with docstrings citing that
   exact requirement — the repository methods were built for this
   purpose but never wired into the service. Found by re-reading the
   SECURITY section against the actual `create()` implementation before
   finalizing the API layer (not caught by live testing, since nothing
   yet exercised the duplicate path with the repository lookups
   already in place to make it look complete). Fixed by adding
   `_reject_duplicate_identifiers()`, raising `ConflictError` on a
   pre-existing hostname, serial number, or MAC address within the
   same organization; different organizations may share an identifier
   freely.

Every other mechanism — real Neo4j node/edge creation and multi-hop
dependency/impact-analysis traversal, asset CRUD end-to-end including
tag assignment and version snapshots, all five import formats and all
six export formats (including the ZIP bundle's download URL from a
real MinIO presigned URL), dynamic group resolution, statistics/
analytics computation, and tenant isolation across organizations — was
verified end-to-end via a live `httpx`-driven smoke test against the
real FastAPI app (real lifespan, real Postgres/Redis/RabbitMQ/
Neo4j/MinIO) before the automated test suite was written, and found no
further defects.
