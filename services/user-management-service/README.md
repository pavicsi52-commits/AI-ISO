# User Management Service

Extended user data and lifecycle for AI-IOS
([`docs/031_Enterprise_User_Management_Service.md.txt`](../../docs/031_Enterprise_User_Management_Service.md.txt)):
profiles, preferences, settings, addresses, contacts, custom metadata,
avatars, tags, internal notes, invitations, bulk CSV/Excel/JSON import
and CSV/JSON/PDF export, and an activity feed. The second AI-IOS
microservice built on `packages/shared-core`, sitting alongside
`services/authentication-service` rather than depending on it.

**Scope note**: this service verifies caller identity tokens but never
issues them, and never calls out to `services/authentication-service`
to provision login credentials — no such integration is named anywhere
in docs/031, which explicitly scopes authentication itself out ("This
service SHALL NOT authenticate users"). Whatever wires "this invited
user can now log in" is a deliberately separate concern, out of scope
here.

## Architecture

Standard service structure per
[`docs/008_Backend_Master_Architecture.md.txt`](../../docs/008_Backend_Master_Architecture.md.txt):
`app/{api,core,config,models,repositories,schemas,services,validators,workers,events,notifications,middleware,telemetry,storage,parsers}`,
`alembic/` (this service's own migrations, same one-schema-per-service
precedent `services/authentication-service` established), `main.py`,
`tests/`.

### Design decisions worth knowing

- **A physically separate database.** `aiios_user_management`, not
  `aiios` — both services define their own `users` table, and a single
  shared Postgres database can't hold two same-named tables in one
  schema. This is genuine "database per service" isolation, not just a
  different schema within one database.
- **JWT verification without issuance.** `app/config/keys.py` holds
  only the RS256 *public* key (`load_public_key`, raising
  `DependencyError` if the file is missing — there is nothing to
  generate here, unlike the auth service's own `keys.py`).
  `get_current_user_id()` decodes a Bearer token's `sub` claim and
  nothing else; there is no cross-service lookup back to
  authentication-service on every request.
- **Self-scoped vs. admin-scoped REST design.** Per docs/031's exact
  endpoint list, profile/preferences/settings/addresses/contacts/
  metadata/avatar/tags/activity are all `/users/...` with **no** `{id}`
  segment — the caller's own JWT `sub` is the implicit target, not a
  path parameter. `notes` is the one exception (`/users/{user_id}/notes`):
  an internal note is admin/manager-authored *about* another user, so it
  genuinely needs an explicit subject. Route **registration order**
  matters here: every literal-path router (`/users/profile`,
  `/users/tags`, ...) must be registered before `user_router`'s catch-all
  `/users/{user_id}`, or FastAPI/Starlette matches the catch-all first
  and a request like `GET /users/profile` gets swallowed as an
  (invalid-UUID) `user_id="profile"` — see `app/core/factory.py`'s
  `create_app()` for the explicit ordering and the bug this fixed.
- **`DEFAULT_ORGANIZATION_ID`** (`app/constants.py`): the exact same
  placeholder UUID `services/authentication-service` uses, documented
  as deliberately identical since both services describe the same
  default tenant until a real Organization service exists.
- **Background import/export as in-process queue jobs.** `POST
  /users/import`/`/export` upload/enqueue only (fast, request-scoped);
  `app/workers/{import,export}_worker.py`'s handlers do the actual
  parsing/row-creation/serialization off the request/response cycle,
  registered as RabbitMQ consumers at startup (`app/core/factory.py`'s
  `_lifespan`) rather than run as a separately deployed process — a
  queue-backed background job either way, just consumed in the same
  process that publishes it.
- **Enum columns come back as plain `str`, not the enum.** Every
  `StrEnum`-typed column here is `mapped_column(String(N))`, matching
  the established convention from `services/authentication-service`.
  Equality/comparison against the enum still works (`StrEnum` members
  *are* strings), but a freshly-loaded row's `.value` attribute access
  fails with `AttributeError: 'str' object has no attribute 'value'` —
  caught in `UserService.transition_status()` and
  `UserExportService.process_job()`; fixed by dropping `.value` in favor
  of `str(x)` (or re-wrapping with the enum constructor where real enum
  behavior was actually needed downstream), not by switching to
  SQLAlchemy's native `Enum` type.
- **Honest "Virus Scan Hook."** `app/storage/avatar_storage.py`
  declares a `VirusScanHook` extension point and reports
  `virus_scan_passed=None` when none is configured — never a fabricated
  `True` — matching the same honesty precedent
  `services/authentication-service`'s sandbox design established.
- **Response-DTO caching, not entity caching.** `UserCacheService`
  caches the serialized response shape for `GET /users/{id}`, not the
  SQLAlchemy entity, avoiding any risk of a cached, detached ORM object
  leaking across requests/sessions.

## Running Locally

```bash
uv sync
# Requires the repository root docker-compose stack running (Postgres,
# Redis, RabbitMQ, MinIO) -- see the repository root README. This
# service also needs its own database created once:
#   docker exec aiios_postgres psql -U aiios -d postgres \
#     -c "CREATE DATABASE aiios_user_management OWNER aiios;"
uv run alembic upgrade head
uv run uvicorn main:app --reload --port 8002
```

Configuration is `AIIOS_`-prefixed environment variables via
`packages/shared-core/config` (see the repository root `.env.example`
for the shared `AIIOS_DATABASE_*`/`AIIOS_REDIS_*`/`AIIOS_RABBITMQ_*`/
`AIIOS_MINIO_*` variables) plus this service's own
`AIIOS_USER_SERVICE_*` variables (`app/config/settings.py`'s
`UserServiceSettings`): `HOST`, `PORT`, `CORS_ALLOWED_ORIGINS`,
`AVATAR_BUCKET`, `IMPORT_EXPORT_BUCKET`, `JWT_PUBLIC_KEY_PATH`. Unlike
the auth service, a missing JWT key file is a hard startup error here —
this service holds no private key to fall back to generating one.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `POST/GET /users`, `GET/PUT/PATCH/DELETE /users/{id}`, `POST /users/search` | Admin CRUD, search, and lifecycle status transitions |
| `GET/PUT /users/profile` | Caller's own extended profile |
| `GET/PUT /users/preferences` | Caller's own platform preferences |
| `GET/PUT /users/settings` | Caller's own application settings |
| `POST/GET/DELETE /users/addresses{,/{id}}` | Caller's own addresses |
| `POST/GET/DELETE /users/contacts{,/{id}}` | Caller's own contact methods |
| `PUT/GET/DELETE /users/metadata{,/{key}}` | Caller's own custom key/value metadata |
| `POST/DELETE /users/avatar` | Caller's own avatar upload/removal |
| `POST/GET/DELETE /users/tags{,/{id}}` | Caller's own tags |
| `GET /users/activity` | Caller's own activity feed |
| `POST/GET/DELETE /users/{user_id}/notes{,/{id}}` | Internal notes *about* another user |
| `POST /users/invite`, `/invite/resend`, `/invite/accept`, `/invite/reject` | Invitation lifecycle |
| `POST /users/import`, `GET /users/import/{id}`, `POST /users/import/{id}/rollback` | Bulk import (CSV/Excel/JSON) |
| `POST /users/export`, `GET /users/export/{id}` | Bulk export (CSV/JSON/PDF) |
| `GET /health` / `/readiness` / `/liveness` | Health checks |
| `GET /metrics` | Prometheus metrics |
| `GET /docs` / `/openapi.json` | OpenAPI documentation |

## Testing

```bash
uv run pytest --cov=app --cov-report=term-missing
```

189 tests, 98.17% coverage, entirely against real infrastructure (the
repository root's docker-compose Postgres/Redis/RabbitMQ/MinIO) — no
mocked database. Postgres isolation between tests uses a per-test
SAVEPOINT (`join_transaction_mode="create_savepoint"` — see
`tests/conftest.py`), the same pattern `services/authentication-service`
established.

`tests/test_worker_regression.py` deliberately steps outside that
SAVEPOINT isolation — it builds its own plain (non-SAVEPOINT) session
factory directly on the real engine, with explicit row cleanup in
teardown — to prove the background import/export workers' commits are
durably visible to a genuinely *separate* connection, not just
flush-visible to the session that wrote them (see "Real bugs found via
live smoke-testing" below). `tests/test_api_import_export.py` stubs out
the queue producer dependency so its HTTP-level tests never publish a
real RabbitMQ message — publishing for real would race the real
in-process consumer against the test's own SAVEPOINT-isolated rows and
against app teardown, which was observed to cause flaky
`ResourceWarning`s; the real publish/consume/commit path is covered
instead by the dedicated worker-regression tests above and was
additionally verified live via `curl`.

## Docker

Build from the **repository root** (this service is a uv workspace
member and its lockfile resolves against the whole workspace):

```bash
docker build -f services/user-management-service/Dockerfile -t aiios/user-management-service .
```

## Real bugs found via live smoke-testing and automated HTTP tests

Per this repository's "start the real service and exercise it" testing
discipline, four real bugs were caught by actually running `uvicorn`
against the real docker-compose stack (driven with `curl`) and by the
automated HTTP-layer test suite — none would have been caught by a test
suite that only exercised services directly against a single shared
in-memory session:

1. **`GET /users/profile` returned a 400 UUID-validation error.**
   FastAPI/Starlette match routes in registration order; `user_router`'s
   `/users/{user_id}` was registered before the literal-path routers
   like `/users/profile`, so every self-scoped request was swallowed as
   an invalid `user_id`. Fixed by registering all literal-path routers
   first (see `app/core/factory.py`'s `create_app()`).
2. **`AttributeError: 'str' object has no attribute 'value'`** in
   `UserService.transition_status()` and
   `UserExportService.process_job()`. A `String`-column-typed enum comes
   back as a plain `str` on a fresh load from a different session — see
   "Design decisions" above.
3. **Import/export jobs were stuck at `"queued"` forever when polled.**
   The background worker built its service with a bare
   `database.session_factory()` call and no explicit commit —
   `BaseRepository.create()`/`update()` only ever `flush()`, by design
   (Unit of Work owns the commit boundary). The worker's own session saw
   its changes; a client polling `GET /users/import/{id}` on an
   independently committed session never did. Fixed by wrapping both
   `_build_import_service`/`_build_export_service` in
   `shared_core.database.session.session_scope`, the exact same class of
   bug `services/authentication-service`'s `get_db_session` had already
   hit and fixed for the HTTP path — this time in the worker path
   instead.
4. **Profile/preference updates never appeared in the activity feed.**
   Caught by `tests/test_api_self_scoped.py::test_activity_list_reflects_prior_operations`
   (`PUT /users/profile` then `GET /users/activity` returned `[]`).
   docs/031's "USER ACTIVITY" section explicitly lists "Profile Updates"
   and "Preference Changes" as tracked activity types, but
   `UserProfileService.update()`/`UserPreferencesService.update()` never
   called `UserActivityService.record()`. Fixed by threading
   `UserActivityService` through both, the same way `UserService`
   already recorded "Status Changes".

## Troubleshooting

- **`sqlalchemy.exc.ProgrammingError: relation "users" already exists`
  on `alembic upgrade head`**: this service's migrations must run
  against `aiios_user_management`, not `aiios` — confirm
  `AIIOS_DATABASE_NAME` before running Alembic, since the two services'
  `users` tables cannot coexist in one schema.
- **`DependencyError: JWT public key not found`** on startup: unlike
  the auth service, this one never generates a keypair. Point
  `AIIOS_USER_SERVICE_JWT_PUBLIC_KEY_PATH` at the exact public key file
  `services/authentication-service` is signing with.
- **`minio.error.S3Error: NoSuchBucket`**: buckets are created lazily on
  first upload (`StorageWrapper.upload`), not at startup — this only
  surfaces if something reads before anything has ever written.
