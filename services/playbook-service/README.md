# Playbook Service

Enterprise playbook service for AI-IOS
([`docs/041_Enterprise_Playbook_Service.md`](../../docs/041_Enterprise_Playbook_Service.md)):
a centralized automation content repository — storage, semantic
versioning, dependency resolution (with real circular-dependency
detection), structural content validation, Ed25519 digital signatures,
draft review and multi-type approval workflows, folder-organized
repository management, and analytics/reporting. Execution belongs to
`services/automation-service`, not this service. The twelfth AI-IOS
microservice built on `packages/shared-core`, following
`services/authentication-service`, `services/user-management-service`,
`services/rbac-service`, `services/organization-service`,
`services/project-service`, `services/secrets-management-service`,
`services/inventory-service`, `services/discovery-service`,
`services/asset-management-service`,
`services/configuration-management-service`, and
`services/automation-service`.

## Architecture

Standard service structure per
[`docs/008_Backend_Master_Architecture.md.txt`](../../docs/008_Backend_Master_Architecture.md.txt).
Every domain-specific directory docs/041's own DIRECTORY STRUCTURE
names (`playbooks/`, `roles/`, `collections/`, `scripts/`, `templates/`,
`tosca/`, `helm/`, `kubernetes/`, `artifacts/`, `versions/`,
`dependencies/`, `validation/`, `linting/`, `security/`, `approval/`,
`publishing/`, `repository/`, `metadata/`, `search/`, `analytics/`,
`reports/`, …) is present but empty — the same "aspirational skeleton,
real code goes flat" precedent every prior AI-IOS service established.
Everything actually lives in the flat
`app/services/`/`app/repositories/`/`app/models/`/`app/schemas/`
layout, with a few directories genuinely distinct from ordinary CRUD:

- `app/signing/signer.py` — real Ed25519 sign/verify/fingerprint built
  directly on `cryptography` (no `shared_core` equivalent exists —
  `shared_core.security.encryption` only does AES-GCM/RSA-OAEP
  *encryption*, `shared_core.security.hashing` only does HMAC), the
  same precedent `services/secrets-management-service`'s own
  `ssh/keygen.py` established for this monorepo's other Ed25519 use.
- `app/validators/content_validator.py` — real, non-executing
  structural validation: `yaml.safe_load`/`safe_load_all` plus
  required-key checks for the nine YAML-shaped content types,
  `ast.parse()` for Python (never `exec`/`eval`), real `sh -n`/`bash -n`
  subprocess syntax checks for Shell/Bash, and a real PowerShell AST
  parser (`[System.Management.Automation.Language.Parser]::ParseFile`)
  via `pwsh`/`powershell.exe` when available, an honest "not available"
  message otherwise. Terraform is explicitly unsupported (docs/041
  itself flags it "(future)"); Custom Plugin content has no defined
  shape anywhere in the spec, so it's honestly always valid.
- `app/services/dependency.py` — real depth-first traversal for
  circular-dependency detection: a `PLAYBOOK`-type dependency's declared
  *name* is resolved to actual same-organization playbooks, and their
  own dependencies are walked looking for a path back to the
  originating playbook.

### Design decisions worth knowing

- **20 tables, confirmed by direct line-by-line reading of docs/041's
  own DATABASE TABLES list** — every one created.
- **`current_version` is deliberately not named `version`** —
  `BaseModel`'s own inherited optimistic-concurrency integer column
  already owns that name; `Playbook.current_version` (a version
  *string*, e.g. `"1.2.0"`) follows the same precedent
  `ConfigurationProfile.profile_version` already established.
- **A domain-model naming collision was caught and fixed proactively,
  before it could become a bug.** The "playbook repository/folder"
  concept from docs/041's own REPOSITORY section would naturally be
  called `PlaybookRepository` — colliding with the standard
  `{ModelName}Repository(BaseRepository[ModelName])` naming convention
  for the `Playbook` model's own database-access class. Caught via
  design reasoning before writing the repositories layer; the *model*
  was renamed to `PlaybookRepositoryFolder` (table name `playbook_repository`
  unchanged, matching docs exactly), the same "rename the model, not
  the repository-pattern class" precedent
  `ConfigurationGitRepository` already established.
- **A version's checksum is what gets signed, never the raw content.**
  `PlaybookVersion.checksum` (`sha256_hex` of content) is computed once
  at version-creation time; `PlaybookSignature.checksum` stores the
  checksum that was signed, `PlaybookSignature.signature` stores the
  base64 Ed25519 signature over that checksum string.
- **No auto-generation fallback for the signing keypair.** Both the JWT
  verification key and this service's own Ed25519 signing keypair are
  loaded from local files at startup with no fallback — a missing file
  is a hard `DependencyError`, never silently regenerated, since a
  rotating signing identity on every container restart would silently
  break every prior signature's own `public_key_fingerprint` continuity.
  Matches `services/secrets-management-service`'s own
  `app/config/master_key.py` precedent.
- **"Validation Engine" resolved the same way docs/039 already
  resolved the identical contradiction.** Docs/041's own "DO NOT
  IMPLEMENT" section names "Validation Engine" while its own
  "VALIDATION"/ACCEPTANCE CRITERIA/OUTPUT sections require one — read
  together, this means a real *structural* (parse-and-check-shape)
  validator that never executes untrusted content, not a runtime
  execution engine (that belongs to `services/automation-service`,
  separately excluded in the same "DO NOT IMPLEMENT" section as
  "Automation Execution").
- **"Integrate Prompt 032" (RBAC) / "Integrate Prompt 035" (Secrets)
  are satisfied without a live HTTP client to either service** — the
  same interpretation docs/039 and docs/040 already established for
  identical SECURITY-section wording: authentication (`CurrentUserId`)
  plus organization/project-scoped queries on every list/search/
  analytics call. No field anywhere in this service's own data model
  stores a secrets-management-service reference; the signing keypair is
  this service's own key material, loaded from a local file exactly
  like the JWT verification key.
- **Validation runs synchronously, inline, within each request** — no
  background worker exists for this service. Unlike
  `services/automation-service`'s durable `automation_execution_queue`,
  docs/041 names no dedicated queue-worker-shaped capability, and
  structural validation (parse-and-check-shape, never execution) is
  fast enough not to need one.
- **Route-registration-order hazard, confirmed live for the third
  time.** `GET /playbooks/{playbook_id}` is a catch-all that matches
  any single path segment, so `search_router`/`templates_router`/
  `repository_folders_router`/`statistics_router`/`reports_router` must
  register before `playbooks_router` in `app/core/factory.py`'s
  `create_app()` — verified with a real HTTP request to
  `/playbooks/search` returning `401` (reaching the search router, not
  a `422` from `playbooks_router` trying to parse `"search"` as a UUID).
- **No REST surface for categories/tags/labels/variables/dependencies/
  roles/scripts/collections/reviews/artifacts/signatures as their own
  top-level resources.** Docs/041's own literal REST APIs list names 16
  operations across 6 paths (`playbooks`, `search`, `templates`,
  `repository`, `statistics`, `reports`); every other sub-resource
  service exists for internal wiring or is reserved for a future
  prompt's own router, and is exercised directly in tests — the same
  "required table, no REST list entry" shape
  `services/automation-service`'s own baselines already established.
  `app/repositories/playbook_artifact.py` in particular has no service
  layer at all above it yet, tested directly at the repository level.

## Running Locally

```bash
uv sync
# Requires the repository root docker-compose stack running (Postgres,
# Redis, RabbitMQ) -- see the repository root README. This service also
# needs its own database created once:
#   docker exec aiios_postgres psql -U aiios -d postgres \
#     -c "CREATE DATABASE aiios_playbook OWNER aiios;"
# ...and its own Ed25519 signing keypair generated once:
#   uv run python -c "from app.signing.signer import generate_signing_keypair as g; \
#     priv, pub = g(); open('keys/signing_private_key.pem','w').write(priv); \
#     open('keys/signing_public_key.pem','w').write(pub)"
uv run alembic upgrade head
uv run uvicorn main:app --reload --port 8012
```

Configuration is `AIIOS_`-prefixed environment variables via
`packages/shared-core/config` (see the repository root `.env.example`
for the shared `AIIOS_DATABASE_*`/`AIIOS_REDIS_*`/`AIIOS_RABBITMQ_*`
variables) plus this service's own `AIIOS_PLAYBOOK_SERVICE_*` variables
(`app/config/settings.py`'s `PlaybookServiceSettings`): `HOST`, `PORT`
(default `8012`), `CORS_ALLOWED_ORIGINS`, `JWT_PUBLIC_KEY_PATH`,
`SIGNING_PRIVATE_KEY_PATH`, `SIGNING_PUBLIC_KEY_PATH`. Redis test
database `14` — distinct from every other AI-IOS service's own test
database (3 authentication, 4 user-management, 5 rbac, 6 organization,
7 project, 8 secrets-management, 9 inventory, 10 discovery, 11
asset-management, 12 configuration-management, 13 automation). Like
every downstream AI-IOS service, a missing JWT public key file — and,
for this service specifically, a missing signing keypair — is a hard
startup error, never silently regenerated.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET/POST /playbooks`, `GET/PUT/DELETE /playbooks/{id}` | Playbook directory and lifecycle |
| `GET /playbooks/{id}/versions` | Version history ("Version History") |
| `POST /playbooks/{id}/approve` | Request and immediately record an approval decision |
| `POST /playbooks/{id}/publish` | Publish a playbook (status transition) |
| `POST /playbooks/import` / `POST /playbooks/export` | Complete playbook definition round-trip, including tags/labels |
| `GET /playbooks/search` | Full-text search, filter, sort, paginate |
| `GET/POST /playbooks/templates` | Reusable playbook content templates |
| `GET /playbooks/repository` | Repository folders ("Folder Organization") |
| `GET /playbooks/statistics` | Organization-wide analytics rollup |
| `GET /playbooks/reports` | Generate a report (6 types) |
| `GET /health` / `/readiness` / `/liveness` | Health checks (readiness includes Postgres connectivity) |
| `GET /metrics` | Prometheus metrics |
| `GET /docs` / `/openapi.json` | OpenAPI documentation |

Every endpoint requires valid authentication (`CurrentUserId`); tenant
isolation is enforced by every list/search/analytics query being scoped
to the `organization_id` the caller supplies, the same shape every
prior AI-IOS service established.

## Testing

```bash
uv run pytest --cov=app --cov-report=term-missing
```

213 tests, 98.42% coverage, entirely against real infrastructure (the
repository root's docker-compose Postgres/Redis/RabbitMQ) — no mocked
database. Postgres isolation between tests uses a per-test SAVEPOINT
(`join_transaction_mode="create_savepoint"`), the same pattern every
prior AI-IOS service established. Digital signatures are exercised with
genuinely real Ed25519 sign/verify via `cryptography` — no live
external dependency, so unlike SSH/Git-provider tests in prior
services, no skip condition is needed. Structural content validation
uses the real `sh`/`bash`/PowerShell interpreters on the host to
syntax-check Shell/Bash/PowerShell content, self-skipping cleanly for
PowerShell assertions that require the interpreter's own presence.

`tests/test_schemas_unrouted.py` directly constructs every schema
backing a concern with no dedicated top-level REST endpoint of its own
(artifacts, audit, categories, collections, dependencies, labels,
reviews, roles, scripts, signatures, tags, variables) — the same
precedent `services/automation-service`'s own identically-named file
established. `tests/test_repository_playbook_artifact.py` and
`tests/test_deps_di_wiring.py` directly exercise the repository and
dependency-injection wiring for capabilities with no service or router
above them at all yet.

## Docker

Build from the **repository root** (this service is a uv workspace
member and its lockfile resolves against the whole workspace):

```bash
docker build -f services/playbook-service/Dockerfile -t aiios/playbook-service .
```

The image installs `bash` (covering Bash-content structural validation;
`sh` is already present, covering Shell Script) but deliberately not
PowerShell Core — the PowerShell validator honestly detects its absence
at request time rather than the image silently pretending to support
it, matching `services/automation-service`'s own runner precedent.

Built and live-health-checked against the real docker-compose network
(`aiios_aiios_network`) — `/health`, `/readiness` (genuine Postgres
connectivity from inside the container), `/liveness`, `/docs`,
`/openapi.json`, and `/metrics` all confirmed responding correctly
end-to-end through the containerized app, plus a live, unauthenticated
request to `/playbooks/search` confirmed reaching the search router
(`401`, not a `422` UUID-parse error) — the route-registration-order
fix proven through the actual running container, not just the test
suite. On Windows/Git Bash, remember `MSYS_NO_PATHCONV=1` ahead of any
`docker run`/`docker exec` whose arguments include a leading-slash
value (e.g. `AIIOS_RABBITMQ_VHOST=/aiios`) — otherwise Git Bash
silently rewrites it into a local filesystem path.

## Real bugs found via testing

1. **Circular-dependency detection silently missed real cycles** —
   `PlaybookDependencyService._creates_cycle()` compared
   `dependency.dependency_type is not DependencyType.PLAYBOOK` using
   Python identity (`is`) on a value freshly fetched from Postgres
   through a plain `String`-backed column (not a SQLAlchemy `Enum`
   type). Since the ORM never coerces a plain-string column back into
   its Python `StrEnum` type on read, the fetched value was a bare
   `str` — value-equal but not identity-equal to `DependencyType.PLAYBOOK`
   — so the check silently skipped every real `PLAYBOOK`-type edge,
   letting a genuine transitive circular dependency through undetected.
   Caught by `test_transitive_cycle_raises_conflict` ("DID NOT RAISE
   ConflictError"), diagnosed via ad-hoc scripts against the real
   database to isolate exactly which boolean was wrong, fixed by
   switching to `!=` with an explanatory comment distinguishing this
   DB-fetched case from the safe identity comparison a few lines above
   (on the raw function *parameter*, never round-tripped through the
   database, which remains correct as `is`). A repository-wide regex
   sweep afterward confirmed no other instance of this exact pattern
   exists elsewhere in `app/`.
2. **`app/telemetry/__init__.py` was missing**, leaving
   `app/telemetry/tracing.py` an implicit namespace-package member
   rather than a proper package — every other prompt's own directory
   convention (`__init__.py` in every `app/` subdirectory) was followed
   everywhere else in this service but was overlooked here. Found not
   through a test failure but through the coverage report itself: the
   module was silently absent from `coverage`'s own file listing
   entirely (not even shown at 0%), rather than appearing in it like
   every sibling module. Fixed by adding the missing empty
   `__init__.py`, after which `app/telemetry/tracing.py` reached 100%
   coverage like every other module.

Every other mechanism — playbook CRUD and status-transition lifecycle
(with correct event publication per transition), semantic versioning
(bump/checksum/structural-validation-gated creation, diff, approval
recording), category/tag/label/variable/template/script/role/
collection/repository-folder CRUD, draft review and multi-type approval
workflows (with correct approve/reject event publication), Ed25519
signing and independent re-verification (both the success and
wrong-key-fails-verification paths), statistics recomputation
(playbook/version counts, validation-results summary, deprecated-content
count, cache-then-recompute semantics), and report generation across
all 6 types — was verified via real integration tests against live
Postgres/Redis/RabbitMQ (not mocks) before this README was written, and
found no further defects.
