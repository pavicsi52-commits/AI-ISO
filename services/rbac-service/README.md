# RBAC Service

Centralized role-based access control and policy evaluation for AI-IOS
([`docs/032_Enterprise_RBAC_Service.md.txt`](../../docs/032_Enterprise_RBAC_Service.md.txt)):
hierarchical roles, a dynamic permission catalog, permission groups,
system/organization/project-scoped role assignment, resource-instance
authorization, an attribute-based policy engine (time/location/IP/
scope/custom conditions), authorization evaluation, caching, events,
notifications, and a full audit trail. The third AI-IOS microservice
built on `packages/shared-core`, alongside `services/authentication-service`
and `services/user-management-service`, and the first service every
other service is expected to call *into* for authorization decisions.

**Scope note**: this service verifies caller identity tokens but never
issues them, and owns no Users/Organizations/Projects data of its own
— every entity here refers to a user/organization/project only by a
bare `UUID`, exactly the same "no cross-service foreign key" pattern
`services/user-management-service` established for its own references
back to `services/authentication-service`.

## Architecture

Standard service structure per
[`docs/008_Backend_Master_Architecture.md.txt`](../../docs/008_Backend_Master_Architecture.md.txt),
extended with the specific sub-packages docs/032's own "DIRECTORY
STRUCTURE" names for this service's authorization *engine* (as opposed
to CRUD orchestration, which still lives in `app/services/` like every
other AI-IOS service):

- `app/roles/hierarchy.py` — pure functions: cycle detection
  (`would_create_cycle`), ancestor-chain resolution, permission
  aggregation across a role hierarchy graph. No database access.
- `app/policies/engine.py` — compiles a persisted
  `AuthorizationPolicy`/`PolicyCondition` row set into a runtime
  predicate, reusing `shared_core.security.policies`' `Policy`/
  `PolicyContext` value objects (see "Design decisions" below for why
  `PolicyEngine.evaluate()` itself isn't used).
- `app/resources/ownership.py` — pure function resolving one resource
  instance's direct grants/denies (owner, shared, public) into a
  decision, or "not decided here" to fall through to role/policy
  evaluation.
- `app/permissions/aggregation.py` — permission code conventions and
  `PermissionScope` (global/organization/project) matching.
- `app/evaluators/authorization_evaluator.py` — the DB-backed
  orchestrator combining all of the above into one allow/deny decision,
  backing both `POST /authorization/evaluate` and `GET
  /users/{id}/permissions`.
- `app/authorization/guard.py` — a FastAPI dependency factory,
  `require_permission(resource, action)`, that runs this same
  evaluator against the *caller's own* identity to protect this
  service's own admin endpoints ("Enforce least privilege" — this
  service authorizes itself with itself, not a separate mechanism).
- `app/services/` — CRUD/orchestration for roles, permissions,
  permission groups, role/permission grants, role assignment
  (system/organization/project scope), policies, and resource grants.
- `app/cache/authorization_cache.py` — the "User Permission Matrix"
  Redis cache, wrapping `shared_core.cache.manager.CacheManager`.
- `alembic/` — this service's own migrations, including a **seed data
  migration** (see below) alongside the schema migration.

### Design decisions worth knowing

- **A complete, seeded permission catalog, not an empty table.** The
  second Alembic migration seeds every `ResourceType` × every
  `PermissionAction` (320 permissions, `"{resource}:{action}"` codes)
  and docs/032's 10 default system roles, then grants each role a
  sensible subset matching its name (Platform Administrator gets
  everything; Viewer gets read-only everywhere; Auditor gets
  read+audit+monitor everywhere; and so on — see the migration's own
  docstring for the exact per-role rule table). Role and permission ids
  are deterministic (fixed UUIDs / `uuid5` of the resource:action pair)
  rather than randomly generated, so every AI-IOS deployment's
  "Platform Administrator" row is the exact same identity, referenceable
  from documentation and other services without a lookup-by-code round
  trip.
- **Authorization precedence, most to least authoritative**: (1) an
  explicit resource-instance grant/deny always wins outright — a deny
  blocks even a role-granted allow, and an explicit allow (ownership,
  direct share, public) grants even where no role would; (2) the
  highest-priority matching policy whose conditions hold, allow or
  deny, wins next; (3) the role/permission baseline — does any of the
  caller's active, unexpired role assignments (aggregated through the
  hierarchy) grant the matching permission. See
  `app/evaluators/authorization_evaluator.py`'s own docstring.
- **`shared_core.security.policies.PolicyEngine.evaluate()` itself
  isn't used**, even though `Policy`/`PolicyContext` are. That engine's
  semantics are "deny if no policies are registered for this action,
  otherwise ALL registered policies must pass" — a good fit for a
  single always-on gate, not for this service's richer model where
  each policy independently carries its *own* allow-or-deny effect and
  multiple policies at different priorities can apply to the same
  action. `app/policies/engine.py`'s `compile_policy()` still produces
  a real `Policy`, but `AuthorizationEvaluator` walks the
  priority-ordered, subject-filtered candidates itself and takes the
  first one whose conditions hold — the effect-aware precedence logic
  shared-core's engine doesn't model.
- **`app/authorization/guard.py` bootstraps itself through real
  evaluation, not a hardcoded superuser check.** Every role/permission/
  policy-management mutation runs through `require_permission(SETTINGS,
  MANAGE)` — docs/032's `ResourceType` list has no dedicated "Roles"
  entry of its own, so role/permission/policy administration is treated
  as platform configuration, the closest listed fit. Role/permission
  assignment on a specific user is gated by `require_permission(USERS,
  ASSIGN/READ)` instead, since it's an action *on a user*. The very
  first Platform Administrator in a fresh deployment must be assigned
  directly against the database (or by a future provisioning script) —
  there is no self-service "become an admin" endpoint, by design.
- **Resource-instance authorization (`resource_permissions`) has no
  REST surface in this prompt.** Docs/032's own endpoint list names
  nothing for managing it directly — it exists to back
  `AuthorizationEvaluator`'s ownership/sharing checks, populated
  through `ResourceAuthorizationService.grant()` today, with an admin
  REST surface left for a later prompt if one is ever named.
- **The `permission_cache` table is a durable snapshot, not the hot
  cache.** The hot lookup path is Redis
  (`app/cache/authorization_cache.py`); the table exists so "what
  permissions did this user actually have at time X" survives a cache
  flush, per docs/032's "User Permission Matrix" caching requirement.

## Running Locally

```bash
uv sync
# Requires the repository root docker-compose stack running (Postgres,
# Redis, RabbitMQ) -- see the repository root README. This service also
# needs its own database created once:
#   docker exec aiios_postgres psql -U aiios -d postgres \
#     -c "CREATE DATABASE aiios_rbac OWNER aiios;"
uv run alembic upgrade head
uv run uvicorn main:app --reload --port 8003
```

Configuration is `AIIOS_`-prefixed environment variables via
`packages/shared-core/config` (see the repository root `.env.example`
for the shared `AIIOS_DATABASE_*`/`AIIOS_REDIS_*`/`AIIOS_RABBITMQ_*`
variables) plus this service's own `AIIOS_RBAC_SERVICE_*` variables
(`app/config/settings.py`'s `RbacServiceSettings`): `HOST`, `PORT`,
`CORS_ALLOWED_ORIGINS`, `JWT_PUBLIC_KEY_PATH`,
`PERMISSION_CACHE_TTL_SECONDS`. Like `services/user-management-service`,
a missing JWT public key file is a hard startup error — this service
holds no private key to fall back to generating one.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET/POST /roles`, `GET/PUT/DELETE /roles/{id}` | Role management, with hierarchy/inheritance |
| `POST/DELETE /roles/{id}/permissions{,/{permissionId}}` | Grant/revoke a permission on a role |
| `GET/POST /permissions`, `PUT/DELETE /permissions/{id}` | Permission catalog management |
| `GET/POST /permission-groups` | Permission group management |
| `POST/DELETE /users/{id}/roles{,/{roleId}}` | Assign/remove a role at system, organization, or project scope |
| `GET /users/{id}/permissions` | A user's aggregated effective permission matrix |
| `POST /authorization/evaluate` | The core allow/deny decision endpoint |
| `GET/POST /policies`, `PUT/DELETE /policies/{id}` | Policy management, with embedded conditions |
| `GET /health` / `/readiness` / `/liveness` | Health checks |
| `GET /metrics` | Prometheus metrics |
| `GET /docs` / `/openapi.json` | OpenAPI documentation |

## Testing

```bash
uv run pytest --cov=app --cov-report=term-missing
```

193 tests, 99.22% coverage, entirely against real infrastructure (the
repository root's docker-compose Postgres/Redis/RabbitMQ) — no mocked
database. Postgres isolation between tests uses a per-test SAVEPOINT
(`join_transaction_mode="create_savepoint"` — see `tests/conftest.py`),
the same pattern every prior AI-IOS service established; every test
automatically sees the seed migration's 10 system roles / 320
permissions / 871 grants for free, since they were already committed
before the SAVEPOINT-isolated transaction began.

## Docker

Build from the **repository root** (this service is a uv workspace
member and its lockfile resolves against the whole workspace):

```bash
docker build -f services/rbac-service/Dockerfile -t aiios/rbac-service .
```

## Real bugs found via live smoke-testing and automated testing

Per this repository's "start the real service and exercise it" testing
discipline:

1. **`policy_conditions.value` was accidentally `NOT NULL`.** The model
   declared `value: Mapped[Any] = mapped_column(JSON, default=None)` —
   in SQLAlchemy 2.0, the *type annotation* (not the Python-level
   `default=`) determines column nullability, and `Mapped[Any]` (not
   `Mapped[Any | None]`) produces a `NOT NULL` column regardless of the
   default. Any condition without an explicit stored value (several of
   the built-in condition-type test fixtures) failed with a real
   `NotNullViolationError` against Postgres. Fixed by annotating
   `Mapped[Any | None]`, with a third Alembic migration altering the
   already-created column.
2. Every other mechanism — role hierarchy with cycle detection,
   permission grants, role assignment and aggregation, resource-grant
   and policy precedence overriding the role baseline, system-role
   deletion protection, and the self-protecting `require_permission`
   guard — was verified end-to-end via live `curl` against a running
   `uvicorn` instance before the automated test suite was written,
   consistent with every prior AI-IOS service in this repository, and
   found no further defects.
