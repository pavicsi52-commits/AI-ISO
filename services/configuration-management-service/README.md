# Configuration Management Service

Enterprise configuration management for AI-IOS
([`docs/039_Enterprise_Configuration_Management_Service.md`](../../docs/039_Enterprise_Configuration_Management_Service.md)):
desired-state configuration profiles, versioning, baselines, drift
detection, compliance, backup/restore/rollback, and GitOps/TOSCA/
Ansible/Kubernetes integration. Per docs/039's own framing:
"Configuration SHALL become the authoritative desired state for
Automation, Validation, Compliance, Monitoring, and AI." The tenth
AI-IOS microservice built on `packages/shared-core`, following
`services/authentication-service`, `services/user-management-service`,
`services/rbac-service`, `services/organization-service`,
`services/project-service`, `services/secrets-management-service`,
`services/inventory-service`, `services/discovery-service`, and
`services/asset-management-service`.

## Architecture

Standard service structure per
[`docs/008_Backend_Master_Architecture.md.txt`](../../docs/008_Backend_Master_Architecture.md.txt).
Every domain-specific directory docs/039's own DIRECTORY STRUCTURE
names (`profiles/`, `templates/`, `baselines/`, `variables/`,
`environments/`, `versions/`, `drift/`, `compliance/`, `backups/`,
`restore/`, `rollback/`, `policies/`, `approvals/`, `analytics/`,
`reports/`, …) is present but empty — the same "aspirational skeleton,
real code goes flat" precedent every prior AI-IOS service established.
Everything actually lives in the flat `app/services/`/
`app/repositories/`/`app/models/`/`app/schemas/` layout, with three
directories genuinely distinct from ordinary CRUD:

- `app/gitops/` — five lean, hand-built REST clients (GitHub, GitLab,
  Azure DevOps, Bitbucket, Gitea), one shared `GitProviderClient`
  Protocol, a URL-parsing `factory.py`, and `credentials.py` (live
  secret resolution against `services/secrets-management-service`,
  never a stored token) — no Git SDK dependency anywhere.
- `app/tosca/`, `app/ansible/`, `app/kubernetes/` — structural content
  validators (TOSCA Simple Profile component shapes, Ansible's own
  dynamic-inventory JSON shape, Kubernetes/Helm/Kustomize manifest
  shapes) with no third-party parser dependency.

### Design decisions worth knowing

- **22 tables, confirmed by direct line-by-line reading of docs/039's
  own DATABASE TABLES list** — every one created.
- **`ConfigurationProfile.profile_version` (not `version`).** `version`
  is already `BaseModel`'s own inherited optimistic-concurrency column;
  this was chosen proactively, unlike the collision this same bug class
  caused in `services/discovery-service`'s own `DiscoverySchedule
  .is_active` and `services/asset-management-service`'s own
  `AssetSoftware.software_version`.
- **Every entity construction site must pass `organization_id`
  explicitly.** `BaseModel`'s inherited `organization_id` column is
  `NOT NULL` with no database or ORM-side default — real integration
  tests caught six services (`assignment`, `compliance`, `backup`,
  `restore`, `rollback`, `change_set`) that built a child entity from
  only its parent `profile_id`, assuming `organization_id` would
  somehow follow. Fixed by fetching the parent profile first (already
  available via each service's own `ConfigurationProfileRepository`
  dependency) and passing `organization_id=profile.organization_id`
  explicitly at every one of those six call sites.
- **`created_by` is never auto-populated by `BaseRepository.create()`'s
  own `actor_id` parameter.** That parameter only feeds the *audit-log*
  side channel (`record_audit`) — it does not set the entity's own
  `created_by` column, which has a plain `default=None`. Caught by a
  real test asserting `ConfigurationChangeSet.created_by` after
  `.create()`; fixed by setting `created_by=created_by` explicitly on
  the `ConfigurationChangeSet` constructor call in
  `ConfigurationChangeSetService.create()`.
- **Secrets are always referenced, never stored.** `ConfigurationGitRepository.credential_ref`/`webhook_secret_ref`
  and `ConfigurationAnsibleInventory.vault_ref` store only a
  `services/secrets-management-service` reference id;
  `GitCredentialResolver` resolves it live, on every sync, forwarding
  the calling user's own Bearer token so that service's own ACL applies
  — the same "resolve live, never persist plaintext" precedent
  `services/discovery-service`'s own `CredentialResolver` established.
  A background (schedule-fired, not interactively-triggered) Git sync
  has no caller identity to forward — `app/workers/git_sync_worker.py`
  honestly skips (and logs) any repository whose `credential_ref` is
  set in that case, the same documented platform gap
  `services/discovery-service`'s own `discovery_worker.py` already
  flagged, rather than inventing a service-account mechanism no prior
  AI-IOS prompt has established.
- **GitOps "Conflict Detection" is real, not a stub.** Once a
  repository has been marked `SYNCED` at least once,
  `ConfigurationGitOpsService.sync_profile()` fetches the remote file's
  *current* content immediately before overwriting it; if that content
  exists and differs from what is about to be written, the sync is
  refused (`ConflictError`, repository marked `CONFLICT`) unless the
  caller passes `force=True`.
- **No MinIO/StorageWrapper.** Configuration data is text/JSON, never a
  large binary blob — `ConfigurationBackup.content` stores the full
  snapshot inline as JSON, keeping this service's infrastructure
  footprint to Postgres/Redis/RabbitMQ only, unlike
  `services/inventory-service`'s own CSV/Excel/ZIP export files.
- **No Neo4j.** Docs/039 names no graph concept for this service,
  unlike `services/asset-management-service`'s own dependency graph.
- **Semantic version bumping is real, not a placeholder counter.**
  `ConfigurationVersionService.create_snapshot()` parses the prior
  snapshot's own `MAJOR.MINOR.PATCH` string and increments the patch
  component; the first snapshot on any branch starts at `1.0.0`.
- **Only Gitea is genuinely live-tested.** Matching AWS/moto's role in
  `services/discovery-service`'s own test suite, Gitea is the one Git
  provider self-hostable via a local Docker container — GitHub/GitLab/
  Azure DevOps/Bitbucket are tested with `pytest-httpx` against their
  real documented response shapes instead, never a live account.
- **Kubernetes "Resource Validation" records an outcome, doesn't gate
  persistence.** Unlike TOSCA/Ansible content (rejected outright with
  `ValidationError` if structurally invalid),
  `ConfigurationKubernetesManifest.validated`/`.validation_errors`
  exist specifically to store a validation *result* — an invalid
  manifest is still persisted, matching what those two columns are for.
- **`GET /configurations/reports` generates a report on request,
  the same "GET-as-generate" shape** `services/asset-management
  -service`'s own `GET /assets/reports` established, rather than
  requiring a separate `POST`.
- **Route registration order is load-bearing.**
  `GET/PUT/PATCH/DELETE /configurations/{id}` shares the exact
  one-segment shape as `/configurations/drift`, `/compliance`,
  `/templates`, `/git`, `/analytics`, and `/reports` — FastAPI/Starlette
  match routes by *shape*, not type, so `profile_router` must be
  registered *after* those six literal-path routers in
  `app/core/factory.py`'s `create_app()`. Documented inline at the
  registration site itself; verified live via `TestClient` before any
  test was written.
- **No REST surface for baselines/variables/environments/policies/
  approvals/TOSCA/Ansible/Kubernetes/audit as their own top-level
  resources.** Docs/039's own literal REST APIs list names 18
  operations across 12 paths; every other sub-resource service exists
  for programmatic completeness (internal wiring — e.g.
  `ConfigurationReportService` calls straight into
  `ConfigurationComplianceService`/`ConfigurationDriftService`/
  `ConfigurationBaselineService`) and is exercised directly in tests,
  the same "required table, no REST list entry" shape
  `services/asset-management-service`'s own owners/contacts/
  procurement/depreciation/firmware/software set already established.

## Running Locally

```bash
uv sync
# Requires the repository root docker-compose stack running (Postgres,
# Redis, RabbitMQ) -- see the repository root README. This service also
# needs its own database created once:
#   docker exec aiios_postgres psql -U aiios -d postgres \
#     -c "CREATE DATABASE aiios_configuration_management OWNER aiios;"
uv run alembic upgrade head
uv run uvicorn main:app --reload --port 8010
```

Configuration is `AIIOS_`-prefixed environment variables via
`packages/shared-core/config` (see the repository root `.env.example`
for the shared `AIIOS_DATABASE_*`/`AIIOS_REDIS_*`/`AIIOS_RABBITMQ_*`
variables) plus this service's own
`AIIOS_CONFIGURATION_MANAGEMENT_SERVICE_*` variables
(`app/config/settings.py`'s `ConfigurationManagementServiceSettings`):
`HOST`, `PORT` (default `8010`), `CORS_ALLOWED_ORIGINS`,
`JWT_PUBLIC_KEY_PATH`, `SECRETS_SERVICE_BASE_URL`,
`HTTP_CLIENT_TIMEOUT_SECONDS`, `DRIFT_DETECTION_INTERVAL_SECONDS`.
Redis test database `12` — distinct from every other AI-IOS service's
own test database (3 authentication, 4 user-management, 5 rbac, 6
organization, 7 project, 8 secrets-management, 9 inventory, 10
discovery, 11 asset-management). Like every downstream AI-IOS service,
a missing JWT public key file is a hard startup error.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET/POST /configurations`, `GET/PUT/PATCH/DELETE /configurations/{id}` | Configuration profile directory and lifecycle |
| `GET /configurations/{id}/versions` | Configuration History |
| `POST /configurations/{id}/rollback` | Roll back to a prior version |
| `POST /configurations/{id}/backup` | Snapshot/backup/export |
| `POST /configurations/{id}/restore` | Restore from a backup |
| `GET /configurations/drift` | Detected configuration drift |
| `GET /configurations/compliance` | Compliance evaluations |
| `GET/POST /configurations/templates` | Reusable configuration templates |
| `GET/POST /configurations/git` | GitOps repository registration/listing |
| `GET /configurations/analytics` | Organization-wide analytics rollup |
| `GET /configurations/reports` | Generate a report (7 types) |
| `GET /health` / `/readiness` / `/liveness` | Health checks (readiness includes Postgres connectivity) |
| `GET /metrics` | Prometheus metrics |
| `GET /docs` / `/openapi.json` | OpenAPI documentation |

Every endpoint requires valid authentication (`CurrentUserId`); tenant
isolation is enforced by every list/search/analytics query being scoped
to the `organization_id` the caller supplies, the same shape every
prior AI-IOS service established.

## Background Workers

Two queue-consumed jobs (`app/workers/`), wired to Prompt 020's
infrastructure only — docs/039 names no dedicated `SCHEDULE MANAGEMENT`
section, so neither pulls in the scheduler framework:

- **`statistics_worker`** — recomputes an organization's cached
  analytics rollup (including the `drift_statistics` aggregate built
  from every already-recorded `ConfigurationDrift` row). Triggered by
  enqueueing `{"organization_id": ...}`.
- **`git_sync_worker`** — synchronizes one profile to one registered
  Git repository. Triggered by enqueueing `{"repository_id": ...,
  "profile_id": ..., "caller_token": <optional>}`.

## Testing

```bash
uv run pytest --cov=app --cov-report=term-missing
```

288 tests, 96.47% coverage, entirely against real infrastructure (the
repository root's docker-compose Postgres/Redis/RabbitMQ, plus a
locally-run Gitea container for GitOps) — no mocked database. Postgres
isolation between tests uses a per-test SAVEPOINT
(`join_transaction_mode="create_savepoint"`), the same pattern every
prior AI-IOS service established. GitHub/GitLab/Azure DevOps/Bitbucket
are tested with `pytest-httpx` against their real documented response
shapes; Gitea is additionally tested live
(`tests/test_gitops_gitea_live.py`, skips automatically if
`AIIOS_TEST_GITEA_TOKEN` is unset):

```bash
docker run -d --name aiios_configmgmt_test_gitea -p 3080:3000 \
    -e GITEA__security__INSTALL_LOCK=true \
    -e GITEA__database__DB_TYPE=sqlite3 gitea/gitea:latest
docker exec -u git aiios_configmgmt_test_gitea gitea admin user create \
    --username aiios-test --password TestPass123! \
    --email aiios-test@example.com --admin --must-change-password=false
# create a token and a "webapp" repo via Gitea's own REST API, then:
export AIIOS_TEST_GITEA_TOKEN=<token> AIIOS_TEST_GITEA_BASE_URL=http://localhost:3080 \
       AIIOS_TEST_GITEA_OWNER=aiios-test AIIOS_TEST_GITEA_REPO=webapp
```

`tests/test_schemas_unrouted.py` directly constructs every schema
backing a service with no dedicated top-level REST endpoint of its own
(baselines, variables, environments, assignments, policies, approvals,
audit, TOSCA, Ansible, Kubernetes) — the same precedent
`services/asset-management-service`'s own identically-named file
established.

## Docker

Build from the **repository root** (this service is a uv workspace
member and its lockfile resolves against the whole workspace):

```bash
docker build -f services/configuration-management-service/Dockerfile -t aiios/configuration-management-service .
```

Built and live-health-checked against the real docker-compose network
(`aiios_aiios_network`) — `/health`, `/readiness` (genuine Postgres
connectivity from inside the container), `/liveness`, `/docs`,
`/openapi.json`, and `/metrics` all confirmed responding correctly
end-to-end through the containerized app.

## Real bugs found via testing

1. **Six services never set `organization_id` when constructing a
   child entity from only its parent `profile_id`.**
   `ConfigurationAssignment`/`ConfigurationCompliance`/
   `ConfigurationBackup`/`ConfigurationRestoreJob`/
   `ConfigurationRollback`/`ConfigurationChangeSet` all inherit a
   `NOT NULL` `organization_id` column with no default, but their own
   services (`assign()`, `evaluate()`, `create_backup()`, `restore()`,
   `initiate()`, `create()`) only ever received a `profile_id` and
   assumed the tenant column would be filled in some other way. Caught
   immediately by real `IntegrityError`s against Postgres the first
   time each service's own test ran. Fixed by having each of those six
   services fetch the parent profile first and pass
   `organization_id=profile.organization_id` explicitly.
2. **`ConfigurationChangeSet.created_by` was never actually set.**
   `BaseRepository.create()`'s own `actor_id` parameter only feeds the
   separate audit-log side channel, not the entity's own `created_by`
   column. Caught by a real test asserting `created_by` after create;
   fixed by setting it explicitly in the constructor call.
3. **`app/gitops/factory.py`'s Azure DevOps URL parser rejected the
   valid 3-segment `organization/project/repo` shape** (requiring 4
   segments unconditionally, even though its own repo-selection logic
   already had a fallback for the no-`_git`-infix case). Caught by a
   real test constructing a client from that exact URL shape. Fixed by
   lowering the minimum to 3 segments and deriving the repo name from
   the last segment when no `_git` infix is present.

Every other mechanism — profile CRUD and version-snapshot recording,
drift/compliance evaluation and event-publication thresholds,
backup/restore checksum verification, rollback initiate/approve/
complete, GitOps registration/sync/conflict-detection across all five
providers (four mocked, one genuinely live), TOSCA/Ansible/Kubernetes
structural validation, policy/approval workflow, statistics
recomputation, and report generation across all 7 types — was verified
via real integration tests against live Postgres (not mocks) before
this README was written, and found no further defects.
