# Project Service

Project lifecycle, membership, roles, templates, and analytics for
AI-IOS
([`docs/034_Enterprise_Project_Service.md`](../../docs/034_Enterprise_Project_Service.md)):
every infrastructure resource, inventory asset, workflow, automation
job, connector, AI agent, report, and dashboard in AI-IOS SHALL belong
to a Project. Projects provide isolation, ownership, governance,
lifecycle management, and collaboration. The fifth AI-IOS microservice
built on `packages/shared-core`, alongside `services/authentication-service`,
`services/user-management-service`, `services/rbac-service`, and
`services/organization-service`.

**A second self-referential tenant root, one level down.** Every
AI-IOS entity carries an inherited (nullable) `project_id` column, per
`shared_core.base.tenant_mixin.TenantMixin`. This service's own
`Project` entity sets its `project_id` equal to its own `id` at
creation — the same self-referential pattern
`services/organization-service` established for its own
`organization_id` one tenant level up — and every child table here
overrides that inherited column to non-nullable plus a real foreign
key back to `projects.id`.

## Architecture

Standard service structure per
[`docs/008_Backend_Master_Architecture.md.txt`](../../docs/008_Backend_Master_Architecture.md.txt).
A few sub-packages specific to this service's domain:

- `app/projects/membership.py` — `rank_at_least()`, the pure ranking
  function behind this service's own admin-gating.
- `app/parsers/` — `json_parser.py`, `yaml_parser.py`, `csv_parser.py`,
  `pdf_writer.py`, `zip_archive.py`: format-specific import/export
  parsing, greenfield (nothing in this monorepo handled YAML or ZIP
  archives before this service).
- `app/workers/` — `import_worker.py`/`export_worker.py`: in-process
  RabbitMQ consumers backing `POST /projects/import`/`/export`'s
  "Background Processing", registered on this service's own queue
  consumer at startup rather than run as a separate deployable process.
- `app/telemetry/tracing.py` — project CRUD, membership changes,
  settings updates, project search, and analytics spans.

### Design decisions worth knowing

- **Dynamic, persisted project roles, not a fixed enum.** Docs/034's
  own "PROJECT ROLES" section requires "Custom Roles" alongside eight
  named defaults (Owner, Administrator, Operator, Automation Engineer,
  Validation Engineer, Developer, Viewer, Auditor) — a fixed three-value
  enum, the shape `services/organization-service` uses for its own
  membership roles, structurally can't represent that. `project_roles`
  is instead a genuinely dynamic catalog: eight system roles seeded
  with fixed ids and a numeric `rank`, plus optional per-project custom
  roles with their own rank. Authorization is still enforced entirely
  within this service (`app/api/deps.py`'s `require_project_admin`/
  `require_project_member`, comparing rank) rather than a live HTTP
  call to `services/rbac-service` — the same "Integrate Prompt 032"
  instruction `services/organization-service` resolved identically for
  its own membership model, and for the same reason: introducing a
  cross-service-calling convention nothing else in this codebase uses
  was judged higher-risk than the value of delegating a rank
  comparison this service can already make correctly.
- **`Project.visibility` genuinely gates access, not just a label.**
  A Private project is invisible to non-members across every read
  endpoint (`GET /projects`, `GET /projects/{id}`,
  `GET /projects/search`) — applying the tenant-isolation lesson
  `services/organization-service`'s own live smoke testing had to
  learn the hard way (a real bug found and fixed there) proactively
  here from the start, rather than repeating the same category of gap.
  Internal/Organization/Public projects remain visible to any
  authenticated platform user, the same directory-level trust
  `services/organization-service`'s own `GET /organizations` grants.
- **A real, previously-undocumented bug class, found live**: the first
  working version of `ProjectImportService`/`ProjectExportService
  .create_job()` relied on the *request's* `session_scope` dependency
  teardown to commit the new job row — but the HTTP handler calls
  `producer.publish()` *immediately* after `create_job()` returns, well
  before that teardown runs. A same-process RabbitMQ round trip is fast
  enough that the in-process worker's `require_by_id()` call
  deterministically arrived before the commit, producing a genuine
  `NotFoundError` on the very first live import test — not a rare
  race. Fixed by having `create_job()` commit immediately, before
  returning to the router. See `app/services/import_service.py`'s own
  docstring and `tests/test_worker_regression.py`'s dedicated
  cross-connection regression tests (which also cover the
  already-known "worker session only flushes, never commits" bug class
  every prior AI-IOS import/export worker already guards against).
- **Ownership transfer updates two things atomically at the API
  layer**: `Project.owner_id` (the authoritative field docs/034's own
  "PROJECT MODEL" names) and the affected membership rows (new owner
  promoted to the Owner role, previous owner demoted to Administrator).
  `PUT /projects/{id}/members/{memberId}/roles` is the one endpoint
  that performs a full ownership transfer when the target role is
  Owner, rather than a dedicated, separately-named endpoint — docs/034
  lists "Transfer Ownership" under both "PROJECT MEMBERS" and "PROJECT
  LIFECYCLE" without naming its own REST path.
- **`business_units`-equivalent scope boundary**: `favorites`,
  `integrations`, `labels`, `metadata`, `preferences`, `notes`, and
  `resources` get full service-layer CRUD but no REST surface —
  docs/034's own endpoint list never names one, the same
  `resource_permissions` precedent `services/rbac-service` established.
- **`project_templates` is organization-scoped, not project-scoped.**
  Docs/034's own REST list names `GET/POST /projects/templates`, not
  `/projects/{id}/templates` — a template isn't owned by one specific
  project, it's a reusable definition available to every project an
  organization creates.
- **Analytics are honestly zero-filled where this service has no
  data.** `ProjectStatisticsService` computes only `member_count` from
  data this service actually owns; every other field docs/034 names
  (automation/workflow/validation/inventory/connector counts, AI/
  storage usage, execution statistics) is left at `0` rather than
  fabricated — those owning services are explicitly out of scope for
  this prompt and don't exist yet in this build, the same honesty
  precedent every prior AI-IOS service's own analytics established.

## Running Locally

```bash
uv sync
# Requires the repository root docker-compose stack running (Postgres,
# Redis, RabbitMQ, MinIO) -- see the repository root README. This
# service also needs its own database created once:
#   docker exec aiios_postgres psql -U aiios -d postgres \
#     -c "CREATE DATABASE aiios_project OWNER aiios;"
uv run alembic upgrade head
uv run uvicorn main:app --reload --port 8005
```

Configuration is `AIIOS_`-prefixed environment variables via
`packages/shared-core/config` (see the repository root `.env.example`
for the shared `AIIOS_DATABASE_*`/`AIIOS_REDIS_*`/`AIIOS_RABBITMQ_*`/
`AIIOS_MINIO_*` variables) plus this service's own
`AIIOS_PROJECT_SERVICE_*` variables (`app/config/settings.py`'s
`ProjectServiceSettings`): `HOST`, `PORT`, `CORS_ALLOWED_ORIGINS`,
`IMPORT_EXPORT_BUCKET`, `JWT_PUBLIC_KEY_PATH`,
`STATISTICS_CACHE_TTL_SECONDS`. Like every downstream AI-IOS service, a
missing JWT public key file is a hard startup error.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET/POST /projects`, `GET/PUT/PATCH/DELETE /projects/{id}` | Project directory and lifecycle |
| `POST /projects/{id}/clone` | Clone a project into a new one |
| `POST /projects/{id}/archive` / `/restore` | Archive/restore a project |
| `GET/POST /projects/{id}/members` | Membership management |
| `DELETE /projects/{id}/members/{memberId}` | Remove a member |
| `PUT /projects/{id}/members/{memberId}/roles` | Assign a role, or transfer ownership |
| `GET/PUT /projects/{id}/settings` | Environment/execution/security policy set |
| `GET /projects/{id}/analytics` | Usage statistics snapshot |
| `GET /projects/search` | Full-text search, filtering, sorting, pagination |
| `GET/POST /projects/templates` | Reusable, versioned project templates |
| `POST /projects/import`, `GET /projects/import/{id}`, `POST /projects/import/{id}/rollback` | Bulk import (JSON/YAML/CSV/ZIP) |
| `POST /projects/export`, `GET /projects/export/{id}` | Bulk export (JSON/YAML/ZIP/PDF) |
| `GET /health` / `/readiness` / `/liveness` | Health checks |
| `GET /metrics` | Prometheus metrics |
| `GET /docs` / `/openapi.json` | OpenAPI documentation |

## Testing

```bash
uv run pytest --cov=app --cov-report=term-missing
```

126 tests, 97.36% coverage, entirely against real infrastructure (the
repository root's docker-compose Postgres/Redis/RabbitMQ/MinIO) — no
mocked database. Postgres isolation between tests uses a per-test
SAVEPOINT (`join_transaction_mode="create_savepoint"` — see
`tests/conftest.py`), the same pattern every prior AI-IOS service
established; every test automatically sees the seed migration's 8
system project roles for free. `tests/test_worker_regression.py`
builds its own plain, non-SAVEPOINT session factory to prove real
cross-connection commit visibility for both bugs documented above.

## Docker

Build from the **repository root** (this service is a uv workspace
member and its lockfile resolves against the whole workspace):

```bash
docker build -f services/project-service/Dockerfile -t aiios/project-service .
```

## Real bugs found via live smoke-testing

Per this repository's "start the real service and exercise it" testing
discipline, found *before* the automated test suite was written, then
covered by dedicated regression tests:

1. **Queue-publish-before-commit race**: `ProjectImportService`/
   `ProjectExportService.create_job()` didn't commit before the request
   handler published the queue message, so the in-process worker's own
   read of the job row could arrive before the commit — a genuine,
   deterministic bug reproduced on the very first live import test, not
   a rare timing coincidence. Fixed by committing immediately inside
   `create_job()`. See "Design decisions" above and
   `tests/test_worker_regression.py`.

Every other mechanism — project creation with automatic Owner
membership, visibility-gated reads, department/team-equivalent
member/role management, ownership transfer's dual field-and-membership
update, clone, archive/restore, every import format (JSON/YAML/CSV/ZIP)
and every export format (JSON/YAML/ZIP/PDF) round-tripped through real
MinIO with presigned download URLs, full-text search with pagination,
and soft-delete-then-404 — was verified end-to-end via live `curl`
against a running `uvicorn` instance before the automated test suite
was written, and found no further defects.
