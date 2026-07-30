# AI-IOS Knowledge Graph Service

Prompt 049. The platform's graph: a Neo4j model of the whole estate,
digital twins, dependency/impact/blast-radius analysis, ten graph
algorithms, synchronization from ten source services, four import/export
formats, snapshots with restore, and full-text search.

Runs on port **8020** against database **`aiios_knowledge_graph`**,
Redis **db 22**, and **Neo4j**.

---

## What this service is

Every other service in the platform knows about its own domain. This one
knows how those domains connect — which application runs on which VM,
which host that VM sits on, and therefore what breaks at 03:00 when the
host does. Two consequences shape everything below: **the graph is
derived, so it must be safe to rebuild**, and **the query surface is a
query language, so it must be safe to expose**.

### `POST /graph/cypher` is the most dangerous endpoint in the platform

It accepts caller-authored Cypher. Three layers stand between a caller
and the database, in this order:

1. **The deployment switch.** `allow_custom_cypher` can turn the
   endpoint off entirely.
2. **[`app/cypher/guard.py`](app/cypher/guard.py).** Refuses write
   clauses, procedure calls, `LOAD CSV`, bare literals, and
   variable-length ranges — *and audits the refusal as `DENIED` before
   returning*.
3. **Neo4j's own read transaction.** The statement runs through
   `session.execute_read`, so a write is refused by the database even if
   the guard missed it.

The guard produces the good error message; Neo4j produces the guarantee.
Neither is sufficient alone, and the difference matters: a guard-only
design is one regex away from a breach, and a database-only design tells
the caller nothing and leaves nothing auditable.

**Bare literals are refused** because a statement containing one cannot
be safely reasoned about — `LIMIT 5` is harmless, `LIMIT 5000000` is
not, and the guard cannot tell which a given number is. Everything a
caller wants to compare against arrives as a bound parameter.

**Variable-length ranges are refused outright.** `[*1..3]` looks bounded
and is: `[*1..50]` looks identical to the parser and will pin the
database. Cypher cannot bind a range as a parameter, so there is no
version of this that is both safe and expressive. The traversal
endpoints take a validated `depth` instead.

### Labels and relationship types cannot be parameterised

Cypher will not bind them, so they are the one thing this service
formats into query text. [`app/cypher/builder.py`](app/cypher/builder.py)
validates every one against the `NodeType`/`RelationshipType` enums
before it goes anywhere near a statement — an allow-list, not an escape
routine. A caller supplying `GraphNode) DETACH DELETE (n` as a node type
is refused by the schema before the builder ever sees it, and by the
builder if it somehow arrives another way.

### Every write is `MERGE`; every delete is `DETACH DELETE`

Synchronization re-runs constantly. `CREATE` would double the graph
every time, so writes `MERGE` on `(key, organization_id)` — the
uniqueness constraint [`app/graph/schema.py`](app/graph/schema.py)
declares — which makes a full re-sync safe to run whenever anyone is
unsure. Deletes detach, because a node removed without its relationships
leaves dangling edges every traversal then has to step around.

### `key` is the identity, not Neo4j's internal id

Internal ids are reused after deletion and explicitly unstable across a
restore, so nothing outside [`app/graph/`](app/graph/) ever sees one.
Relationship keys are *derived* — `from|TYPE|to` — for the same reason,
which also means an edge deleted and recreated by a sync keeps the same
identity in the change log.

### Synchronization reads with a service token, and projects narrowly

A sync runs unattended; there is no caller at 03:00. That is a real
departure from `services/dashboard-service`, which reads every source as
the asking user — and it has a consequence:
[`app/synchronization/mappers.py`](app/synchronization/mappers.py)
projects a deliberately narrow field set. A mapper that copied whole
source rows into the graph would launder privileged data into a store
with different access rules.

Keys are namespaced by source (`inventory:42`), because inventory asset
42 and automation job 42 are different things and merging them produces
a graph that is confidently wrong in a way no error surfaces.

### A full sync deletes, and both guards matter

`SyncMode.FULL` removes nodes the source no longer reports. That is
scoped twice — **to the source**, and **excluding pinned nodes** —
because both unguarded forms look exactly like a working sync until
someone notices half the graph is missing. An incremental sync deletes
nothing at all: absence from a page of changes says nothing about
whether a node still exists.

### Risk is the worst single impact, not the sum

`AnalysisResult.risk_score` takes the **maximum** affected-node impact.
A sum grows with estate size, so a large healthy environment would score
worse than a small fragile one — the opposite of useful. The maximum
answers "how badly is the worst-affected thing hit?", which is the
question that decides whether to page someone.

### Statistics are derived, never incremented

Every figure is recomputed from the graph. Two are worth more than they
look: **orphan count** (nodes with no relationships — almost always a
sync bug rather than a fact about the estate) and **connected
components** (more than one usually means a sync gap, and an estate that
has quietly split into two graphs still answers every single-node query
correctly, so nothing else surfaces it).

### A restore replaces; it does not merge

Restoring a snapshot purges the organization's nodes first, because a
merge would leave behind exactly what someone restoring is trying to
remove. It is therefore destructive: scoped to one organization by
parameter, checksummed before it runs, and never triggered implicitly.

---

## Ceilings, and the mistake they caused four times

Four settings are expressed in **nodes** — `analytics_max_nodes`,
`MAX_SNAPSHOT_NODES`, `max_export_nodes`, `max_import_nodes` — while a
single Cypher read returns at most `MAX_LIMIT_CEILING` (10,000) rows.
Handing a node ceiling straight to a read raises `Limit must be between
1 and 10000`, and four independent callers each made that mistake:
analytics, statistics, snapshot capture, and export were **all broken at
their own default settings**. Snapshot capture had never once produced a
restorable backup.

The fix is structural rather than four patches:
`GraphRepository.collect_graph` is the single paged reader for "give me
the whole graph", and every caller wanting all of it goes through it.
`analytics_max_nodes` is additionally bounded by `MAX_LIMIT_CEILING` in
settings, because those algorithms genuinely need one in-memory graph —
configuring a larger value never bought a larger analysis.

---

## Tenant isolation

Every read is scoped by `organization_id`, including the ones keyed by
something else. That is not decoration: node keys are business
identifiers (`app-1`, `host-1`), so a by-key read without an
organization filter is *guessable*, not obscure. Three such reads
existed and are now scoped, and `GET /graph/export/{id}/download` — which
serves an entire graph — now checks ownership and answers `404` rather
than `403`, because a 403 confirms the id.

---

## Layout

| Path | What lives there |
| --- | --- |
| [`app/cypher/`](app/cypher/) | The injection defence: builder (allow-lists) and guard (read-only enforcement) |
| [`app/graph/`](app/graph/) | Neo4j client, schema, entities, and the repository every write goes through |
| [`app/analytics/`](app/analytics/) | Pure algorithms — degree, betweenness, PageRank, components, communities, risk |
| [`app/dependencies/`](app/dependencies/) | Dependency, impact, and blast-radius traversal with distance decay |
| [`app/digital_twin/`](app/digital_twin/) | A node plus the state PostgreSQL holds about it |
| [`app/synchronization/`](app/synchronization/) | Ten source mappers and the engine that runs them |
| [`app/importer/`](app/importer/), [`app/exporter/`](app/exporter/) | JSON, CSV, GraphML, and Cypher, in both directions |
| [`app/versioning/`](app/versioning/) | Snapshots, version markers, and graph comparison |
| [`app/search/`](app/search/) | Full-text search over the Neo4j index, plus metadata search |
| [`app/services/`](app/services/) | The service layer: graph, query, analytics, statistics, sync, I/O, audit |
| [`app/api/`](app/api/) | 45 operations over 20 paths |

**Router include order matters.** `/graph/topology`, `/graph/statistics`,
and friends are literal segments that would otherwise be parsed as a node
whose key is the word "topology" — see
[`app/api/__init__.py`](app/api/__init__.py).

---

## Running it

```bash
# Migrations first — never baked into CMD, so a multi-replica rollout
# cannot race two containers running the same migration.
uv run alembic upgrade head

uv run uvicorn main:app --port 8020
```

The **Neo4j schema** is applied at startup instead: every statement is
`IF NOT EXISTS`, so unlike a relational migration it is genuinely
idempotent and safe for N replicas to run concurrently.

**Property-existence constraints are Enterprise-only.** The schema
module probes the edition and skips them with an INFO log on Community
rather than attempting and failing.

```bash
docker build -f services/knowledge-graph-service/Dockerfile \
  -t aiios/knowledge-graph-service:0.1.0 .   # context is the repo root
```

The statistics rollup is **leader-elected** through
`shared_core.scheduler`, so every replica starts identically and only
one computes the rollup. That is the opposite of
`services/dashboard-service`'s per-replica refresh loop, and for a
reason: this rollup is a pure database write with no per-replica state,
so N replicas would be N times the load for an identical result.

---

## Testing

699 tests against **real PostgreSQL and real Neo4j**, 95%+ coverage.

Stubbing the driver was never an option here. A stub can confirm this
service *builds* the Cypher it meant to; only a real database confirms
that a write submitted through a read transaction is refused — and that
is the guarantee the most dangerous endpoint rests on.

**Graph isolation is by organization id**, not transaction: Neo4j has no
`SAVEPOINT`, so every test works inside its own tenant and the fixture
purges it afterwards. That has a useful side effect — every test is also
a tenant-isolation test.

### Notes worth keeping

- **The driver is function-scoped.** An `AsyncDriver` built on one event
  loop and used from another fails with `'NoneType' object has no
  attribute 'send'`, which names nothing useful. The schema is cached
  behind a module flag instead, since that is the expensive part.
- **Round-trip testing is the only way to catch export/import
  asymmetry.** Three separate bugs meant this service could not re-import
  its own exports — none visible by reading the code, all of which broke
  snapshot restore. Every format is now round-tripped in tests and again
  live against the container.
- **A request-scoped SAVEPOINT does not roll back the way a real request
  does.** The audit test for refused Cypher passed for as long as the
  behaviour was broken; only a live container revealed that `DENIED`
  entries were being discarded with the transaction that raised. Where a
  test's isolation differs from production's, the test can only be
  trusted about the things that isolation does not touch.
