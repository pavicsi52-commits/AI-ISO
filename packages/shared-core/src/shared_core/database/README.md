# Enterprise Database Framework

Every future microservice inherits database connections, transactions,
repositories, unit of work, pagination, sorting, filtering, soft delete,
audit, versioning, tenant isolation, query utilities, and health checks
from this package rather than reimplementing them
(docs/018_Enterprise_Database_Framework.md.txt). PostgreSQL only. No
business tables, no business logic -- a concrete service brings its own
models and repositories built *on top of* this framework, never a copy of
it.

## Database Framework Guide

```python
from shared_core.database import create_database_framework
from shared_core.config.settings import DatabaseSettings

framework = await create_database_framework(DatabaseSettings())  # waits for DB to be ready
health = await framework.check_health()          # DatabaseHealthReport
async with framework.session_factory() as session:
    ...
await framework.shutdown()                        # at service shutdown
```

`create_database_framework()` is the one call a service's startup makes:
it builds the engine, waits (with retry/backoff) for the database to accept
connections, and hands back a `DatabaseFramework` bundling the engine and
session factory. `create_test_database_framework(dsn)` is the equivalent
for tests (SQLite or a real Postgres test database, no wait-for-ready).

## Base Model Guide

```python
from shared_core.database import BaseModel
from sqlalchemy.orm import Mapped, mapped_column

class Asset(BaseModel):
    __tablename__ = "assets"
    name: Mapped[str] = mapped_column()
```

`BaseModel` already carries `id` (UUID), `created_at`/`updated_at`,
`created_by`/`updated_by`/`deleted_by`, `deleted_at`, `version`,
`is_active`, `organization_id`/`project_id` -- "No future entity may
redefine these fields." A concrete entity only ever adds its own columns.

## Repository Guide

```python
from shared_core.database import BaseRepository, TenantScope

repo = BaseRepository(session, Asset, tenant_scope=TenantScope.from_security_context())
asset = await repo.create(Asset(name="server-1", organization_id=org_id))
asset = await repo.get_by_id(asset.id)             # None if not found (or outside tenant scope)
asset = await repo.update(asset, expected_version=asset.version)
await repo.delete(asset.id)                         # soft delete
await repo.restore(asset.id)
results = await repo.search(["name"], "server", mode=SearchMode.TRIGRAM)
page = await repo.paginate(page=1, page_size=20, filters=[...], sort_fields=[...])
created = await repo.bulk_create([Asset(...), Asset(...)])
affected = await repo.bulk_delete([id1, id2])
```

`BaseRepository` is generic over every entity -- "No business-specific
repositories" reimplement CRUD, bulk operations, search, or pagination.
Passing `tenant_scope` makes every query it builds automatically
organization/project-filtered; omit it for platform-internal, intentionally
cross-tenant tooling. Every write is audited automatically (see below) and
every update enforces optimistic locking when `expected_version` is given.

## Query Builder Guide

```python
from shared_core.database import QueryBuilder, SearchMode

builder = (
    QueryBuilder(Asset)
    .where(Asset.is_active.is_(True))
    .where_in("status", ["active", "pending"])
    .search(["name", "description"], "gpu server", mode=SearchMode.FULL_TEXT)
    .order_by([SortField("created_at", SortDirection.DESC)])
)
page = await builder.paginate(session, page=1, page_size=20)
count = await builder.count(session)
```

`QueryBuilder` is a fluent facade over `filtering`/`sorting`/`search` plus
AND/OR/NOT/IN/BETWEEN/subquery/EXISTS/aggregation primitives that don't
have a dedicated module of their own. Every method builds a SQLAlchemy
expression tree against bind parameters -- "Parameterized Queries only,"
never string interpolation.

## Pagination, Filtering, Sorting, Search Guide

```python
from shared_core.database import (
    Filter, FilterOperator, apply_filters,
    SortField, SortDirection, apply_sorting, parse_sort_expression,
    paginate_by_offset, paginate_by_cursor,
)

filters = [Filter("status", FilterOperator.EQUAL, "active")]
sort_fields = parse_sort_expression("created_at:desc:nulls_last,name:asc")
page = await paginate_by_offset(session, stmt, page=1, page_size=20)          # admin tables
feed = await paginate_by_cursor(session, stmt, Asset, cursor=next_cursor)     # infinite scroll
```

Offset pagination (`page`/`page_size`, with `total`/`has_next`/`has_previous`
metadata) suits jump-to-page admin UIs. Cursor pagination is keyset-based on
a `datetime` column plus `id` as a tiebreaker -- stable under concurrent
inserts, where offset pagination can skip or repeat rows. `SearchMode.ILIKE`
always works; `FULL_TEXT` and `TRIGRAM` are PostgreSQL-only (the latter
needs the `pg_trgm` extension enabled).

## Transaction / Unit of Work Guide

```python
from shared_core.database import UnitOfWork
from shared_core.database.transaction import unit_of_work, nested_transaction, run_with_retry

async with UnitOfWork(session_factory) as uow:      # begin/commit/rollback/cleanup
    uow.session.add(entity)
    async with uow.nested():                         # SAVEPOINT -- inner failure only
        ...                                           # rolls back the savepoint

async with unit_of_work(session, timeout_seconds=5):  # lower-level primitive
    ...

result = await run_with_retry(operation, max_attempts=3)  # deadlock/serialization retry
```

`UnitOfWork` is the object-oriented entry point business/service code uses
directly -- "Every business operation must use Unit of Work." It's built on
the lower-level `unit_of_work()`/`nested_transaction()`/`run_with_retry()`
primitives in `shared_core.database.transaction`, which remain available
for callers that already hold a session.

## Tenant Isolation Guide

```python
from shared_core.database import TenantScope, apply_tenant_scope, enforce_tenant_match

scope = TenantScope.from_security_context()   # reads the request's SecurityContext
stmt = apply_tenant_scope(stmt, Asset, organization_id=scope.organization_id, is_super_admin=scope.is_super_admin)
enforce_tenant_match(asset, organization_id=scope.organization_id)  # defense in depth after get_by_id
```

Every query automatically filters by organization/project when a
`TenantScope` is supplied; an unscoped, non-super-admin query raises
`TenantViolationError` rather than silently returning every tenant's data.
"No bypass unless Super Admin."

## Soft Delete, Audit, Versioning Guide

```python
from shared_core.database import mark_deleted, mark_restored, purge
from shared_core.database import record_audit, capture_before, snapshot
from shared_core.database import check_version, increment_version

before = capture_before(entity)   # pre-flush column snapshot for changed attrs
record_audit("update", entity, before=before, actor_id=user_id)
check_version(entity, expected_version)   # raises VersionConflictError on mismatch
```

Delete never removes a row -- `deleted_at`/`deleted_by`/`is_active=false`.
`purge()` issues a real `DELETE`, reserved for retention-policy cleanup of
already-soft-deleted records. Audit entries are emitted as structured log
events via `shared_core.logging`'s `.audit()` method (not a database
table -- this framework creates no business tables). Versioning is
optimistic-locking only: `BaseRepository` calls `check_version`/
`increment_version` automatically; call them directly only outside the
repository.

## Migration Guide

```python
from shared_core.database.migration import (
    build_alembic_config, upgrade, downgrade, generate_revision,
    get_migration_status, validate_migrations,
)

config = build_alembic_config(script_location="alembic", dsn=settings.dsn)
upgrade(config, "head")
status = await get_migration_status(engine, config)   # current vs. head revision
```

This package owns no business schema, so it ships no `migrations/`
directory of its own -- each service owns its own Alembic `script_location`
(`env.py` + `versions/`) with its own `target_metadata`. What's here is the
plumbing every service's migration tooling shares: building `Config`
consistently, wrapping Alembic's command API in framework exceptions
(`MigrationFailedError`) instead of bare Alembic ones, and read-only
status/history/validation queries. Alembic's command API is synchronous, so
it runs over `psycopg` rather than the `asyncpg`-based engine the rest of
this framework uses -- the standard "asyncpg for the app, psycopg for
migration tooling" split. "Never modify production schema manually."

## Seed / Fixture Guide

```python
from shared_core.database.seed import SeedRegistry, SeedEnvironment, seed
from shared_core.database.fixtures import ModelFactory

registry = SeedRegistry()

@seed(registry, "default_roles", SeedEnvironment.DEVELOPMENT)
async def _seed_default_roles(session: AsyncSession) -> None: ...

await registry.run(session, SeedEnvironment.DEVELOPMENT)

class AssetFactory(ModelFactory[Asset]):
    model = Asset
    @classmethod
    def default_values(cls) -> dict:
        return {"name": f"asset-{cls.next_sequence()}", "organization_id": uuid4()}

asset = await AssetFactory.create(session)
```

No concrete seed data lives in this framework -- that would be business
logic. `SeedRegistry` is the mechanism every service organizes its own
seeds around; `ModelFactory` is the base every service's test factories
subclass.

## Database Health Guide

```python
from shared_core.database import check_database_health, get_health_report, get_pool_status

status, latency_ms = await check_database_health(engine)   # cheap: connectivity + latency
report = await get_health_report(engine)                    # + server version + pool status
```

## Developer Guide

### Decorators

```python
from shared_core.database.decorators import transaction, readonly, tenant, audit, soft_delete, retry

@transaction
async def create_asset(session: AsyncSession, ...): ...

@readonly           # guarantees no durable writes -- rolls back unconditionally
@tenant()            # enforces organization_id matches the caller's SecurityContext
@retry(max_attempts=3)   # exponential backoff on deadlock/serialization failures
```

Imported from `shared_core.database.decorators` (not the package root) --
`transaction`/`audit` re-export Prompt 012's `shared_core.decorators`
implementations rather than duplicating them; the module-root `__init__.py`
doesn't re-export any of these six because their names would otherwise
shadow this package's own `transaction`/`seed` submodule attributes.

### Helpers

`shared_core.database.helpers` has the small, dependency-free primitives
(`new_uuid`, `utcnow`, `build_like_pattern`, `normalize_page_params`,
`sanitize_search_term`, `migration_file_slug`) that the richer
`pagination`/`filtering`/`search`/`sorting` modules build on.

## Architecture Notes

- **PostgreSQL only.** No SQLite-specific production code path; SQLite is
  used only for fast unit tests of the SQLite-portable generic paths.
  JSONB filtering, full-text/trigram search, and the Alembic migration
  framework are tested against the real `docker-compose` PostgreSQL
  container.
- **No circular imports**: `security` -> nothing here; this package depends
  one-directionally on `shared_core.security.context` (for tenant scope and
  actor IDs) and `shared_core.logging` (for audit events), never the
  reverse.
- **`unit_of_work` naming**: the low-level context-manager function lives
  at `shared_core.database.transaction.unit_of_work` rather than being
  re-exported at the package root -- this package already has a
  same-named `unit_of_work.py` submodule (home of the higher-level
  `UnitOfWork` class, which *is* exported at the root). Re-exporting both
  under the same name would have one silently shadow the other depending
  on import order.
- **Audit persists nowhere**: audit entries are structured log events
  (`shared_core.logging`), not a database table -- this framework must not
  create business tables, and a write-once audit trail is exactly what
  structured logging (shipped to a log pipeline) is for.
- **Migrations run over `psycopg`, the app runs over `asyncpg`**: Alembic's
  command API (`upgrade`/`downgrade`/`revision`) is fundamentally
  synchronous; rather than reimplementing it against an `AsyncEngine`, this
  framework uses the standard dual-driver split.
