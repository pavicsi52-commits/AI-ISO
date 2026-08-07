# AI-IOS Enterprise Plugin Marketplace Service

Prompt 059. Plugin registration and lifecycle, manifest validation,
packaging and Ed25519 signing, DB-driven dependency resolution,
sandboxed execution governance, installation lifecycle, capability
permissions, publisher trust, marketplace listings, reviews/ratings,
and analytics/reports/audit.

Runs on port **8030** against database **`aiios_plugin_marketplace`**
and Redis **db 32**.

---

## What this service is

Every plugin AI-IOS can extend itself with is modeled here as two
distinct entities: a *definition* (`Plugin` — registered, validated,
published, approved by its own authoring organization) and, separately,
an *installation* (`PluginInstallation` — a different organization's
own installed instance, configured, activated, upgraded, rolled back,
disabled, removed independently of the definition it came from). This
is the same "author owns the catalog entry, installer owns their own
instance" split integration-hub-service's own `ConnectorMarketplaceEntry`/
`Connector` pair already established in Prompt 058.

### Reused frameworks vs genuine gaps

Established by a dedicated research pass before any code was written
(see `AI_MEMORY.md`'s own Prompt 059 entry for exact source citations):

- **Reused directly:** `shared_core.plugins.versioning`
  (`is_upgrade`/`is_downgrade`/`parse_version` — the same real semver
  comparison Prompt 058 already reused, applied here to plugin
  version/installation upgrade and rollback); `shared_core.plugins
  .sandbox.PluginSandbox` (execution-timeout wrapping and best-effort
  process memory monitoring only — see below for why its own
  permission/filesystem/network checks are *not* reused);
  `shared_core.storage.wrapper.StorageWrapper` (MinIO — packaged
  artifact storage); `shared_core.security.certificates` is available
  but unused (see "What's deliberately out of scope"); `shared_core
  .scheduler` (all four background workers); `shared_core.events` (the
  10 domain events).
- **Genuine gaps, built new:** manifest validation against docs/059's
  own richer field set — Publisher, split Category+Type, structured
  multi-platform Supported-Platform-Versions, plural Entry Points, API
  Requirements, Health Checks, Checksum — none of which
  `shared_core.plugins.manifest.PluginManifest` covers
  ([`app/manifests/engine.py`](app/manifests/engine.py)); a real
  DB-backed dependency graph with DFS cycle detection spanning
  organizations, mirroring `playbook-service`'s own
  `PlaybookDependencyService._creates_cycle` rather than
  `shared_core.plugins.resolver.DependencyResolver`'s in-memory-only
  scope ([`app/dependencies/engine.py`](app/dependencies/engine.py));
  tar.gz/zip packaging and checksumming — no `shared_core.plugins`
  module compresses or archives anything
  ([`app/packages/engine.py`](app/packages/engine.py)); Ed25519
  signing, mirroring `playbook-service/app/signing/signer.py` exactly
  rather than `shared_core.plugins.manifest`'s RSA-PSS scheme, which is
  keyed to a different manifest shape
  ([`app/security/signer.py`](app/security/signer.py)); a bespoke
  `PluginPermissionCategory`-keyed capability-grant model, since
  `shared_core.plugins.permissions.PluginPermission`'s nine values
  don't cover docs/059's own eleven (Inventory/Automation/Workflow/
  Secrets/Knowledge-Graph/Monitoring/Notification/API/Filesystem/
  Network/Custom); a first-class `plugin_publishers` table and
  `plugin_reviews`/`plugin_ratings` public star-rating system — neither
  has any precedent anywhere else in the monorepo (`playbook-service`'s
  own `PlaybookReview` is an internal draft-approval step, not a
  post-publish public review).

### The sandbox reuses timeouts and memory monitoring, not permission checks

`shared_core.plugins.sandbox.PluginSandbox.check_permission`/
`.check_filesystem_access`/`.check_network_access` are keyed to
`shared_core.plugins.permissions.PluginPermission` — a nine-value
vocabulary that doesn't line up with this service's own eleven-value
`PluginPermissionCategory`. Forcing a bridge between two partially-
overlapping enums would have been more fragile than it's worth, so
[`app/sandbox/engine.py`](app/sandbox/engine.py)'s `PluginExecutionSandbox`
reuses `PluginSandbox` only for what's genuinely permission-vocabulary-
agnostic — `run`'s `asyncio.wait_for` timeout wrapper and
`check_memory_usage`'s `psutil` monitoring — and implements its own
`check_granted`/`check_filesystem_access`/`check_network_access` keyed
directly to `PluginPermissionCategory`. Real local-process execution
(`asyncio.create_subprocess_exec`, never `shell=True`) mirrors
`automation-service/app/runners/subprocess_helper.py`'s own pattern,
rewritten rather than imported per this platform's zero-cross-service-
import convention.

### Two permission models, two different jobs

`plugin_permissions` (`PluginPermissionGrant`, this service's own
bespoke table) is the audit/approval trail — what an organization has
actually granted one of its own installations, decided by a human via
`POST .../grant`/`.../deny`/`.../revoke`. `PluginExecutionPolicy
.granted_categories` (in `app/sandbox/engine.py`) is the runtime
enforcement layer a caller builds from that grant table before
executing a plugin's own entry point. They're deliberately two
different types, not one shared across a DB row and a runtime check.

---

## Layout

| Path | What lives there |
| --- | --- |
| [`app/manifests/`](app/manifests/) | Manifest validation against docs/059's own richer field set — a genuine gap, built new |
| [`app/dependencies/`](app/dependencies/) | Real DB-backed dependency-graph cycle detection — a genuine gap, built new |
| [`app/packages/`](app/packages/) | tar.gz/zip packaging + checksumming — a genuine gap, built new |
| [`app/sandbox/`](app/sandbox/) | Execution governance: `PluginSandbox` reuse (timeout/memory) + bespoke permission checks |
| [`app/security/`](app/security/) | `signer.py` — Ed25519 signing, mirroring `playbook-service` |
| [`app/models/`](app/models/) | 17 tables |
| [`app/repositories/`](app/repositories/) | 17 repositories, `require_in_org` named apart from the base's unscoped `require_by_id` |
| [`app/services/`](app/services/) | 10 modules, 12 service classes |
| [`app/api/`](app/api/) | 45 routes across 6 routers under `/plugins/*` plus health — the 15 literal docs/059 endpoints live in `app/api/plugins.py` |
| [`app/workers/`](app/workers/) | Health probe sweep, marketplace approval sweep, statistics rollup, review moderation sweep — all leader-elected |

### The router-registration order matters

`plugins_router` owns the catch-all `GET`/`PUT`/`DELETE /plugins/{plugin_id}`.
FastAPI/Starlette matches routes in registration order across the
*whole* app, not per-router, so `app/api/__init__.py` registers every
router with a static one-segment path under `/plugins/...`
(`publishers_router`, `installations_router`, `marketplace_admin_router`)
*before* `plugins_router` — otherwise a request to e.g.
`GET /plugins/publishers` gets hijacked into `get_plugin` with
`plugin_id="publishers"` and fails UUID parsing. The same
router-ordering bug class already found and fixed in
notification-center-service; found here by one of the test-writing
agents while covering the publishers/marketplace-admin/health routes.

---

## Running it

```bash
docker build -t aiios/plugin-marketplace-service:0.1.0 \
  -f services/plugin-marketplace-service/Dockerfile .

docker run -d --name aiios_plugin_marketplace \
  --network aiios_aiios_network -p 8030:8030 \
  -e AIIOS_DATABASE_HOST=aiios_postgres -e AIIOS_DATABASE_PORT=5432 \
  -e AIIOS_DATABASE_NAME=aiios_plugin_marketplace \
  -e AIIOS_DATABASE_USER=aiios -e AIIOS_DATABASE_PASSWORD=change-me \
  -e AIIOS_REDIS_HOST=aiios_redis -e AIIOS_REDIS_DB=32 \
  -e AIIOS_REDIS_PASSWORD=change-me \
  -e AIIOS_RABBITMQ_HOST=aiios_rabbitmq -e AIIOS_RABBITMQ_USER=aiios \
  -e AIIOS_RABBITMQ_PASSWORD=change-me -e AIIOS_RABBITMQ_VHOST=/aiios \
  -e AIIOS_MINIO_HOST=aiios_minio -e AIIOS_MINIO_ACCESS_KEY=aiios \
  -e AIIOS_MINIO_SECRET_KEY=change-me-min-8-chars \
  aiios/plugin-marketplace-service:0.1.0
```

Migrations: `uv run alembic upgrade head`. `keys/jwt_public_key.pem` is
the public half of `services/authentication-service`'s signing key —
this service verifies but never issues tokens.

**`MSYS_NO_PATHCONV=1` is required on any `docker run` call whose
arguments contain a leading `/`** (e.g. `AIIOS_RABBITMQ_VHOST=/aiios`) —
Git Bash on Windows otherwise silently rewrites it into a Windows path
(`/aiios` → `C:/Program Files/Git/aiios`) before Docker ever sees it,
producing an opaque `AMQPInternalError` at RabbitMQ connection time with
no indication the vhost itself was ever mangled.

Redis's own `--databases` count in the root `docker-compose.yml` was
raised from 32 to 64: with 32 total (indices 0–31), integration-hub-
service's own db 31 was already the last valid index, leaving this
service's own db 32 out of range — and every one of Prompts 060–080
would have hit the same ceiling in turn.

Verified live against the real stack, through the actual built image:
registered a plugin, submitted and validated a manifest, published it,
created a draft marketplace listing, installed and activated it, then
— **without ever calling the manual approve or probe endpoints** —
watched the leader-elected marketplace-approval-sweep worker flip the
listing from `draft` to `published` on its own within one 10-second
tick, and watched the health-probe-sweep worker pick the installation
up and record a real `unknown`-then-`healthy` transition on its own
across two ticks (the first tick genuinely fired *before* a
`health_check_url` was even configured, correctly recording `unknown`
with an explanatory error rather than a fabricated result) — the same
"does the worker actually fire without being manually triggered" check
webhook-service's own Prompt 057 build first established and every
service since has reproduced. Auth used a throwaway RSA keypair mounted
over the bundled `jwt_public_key_path`, not `services/authentication
-service`'s own real private key — confirmed after the fact that the
real key (`services/authentication-service/keys/jwt_private_key.pem`)
does verify correctly against this service's own bundled public key,
so either would have worked. Live-verification rows cleaned from every
table they touched before the final test-suite re-run.

That same live pass also caught a real bug: `PluginInstallationService
.configure()` unconditionally set `status = CONFIGURED` on every call,
which silently knocked an already-`ACTIVE` installation out of
`list_all_active`'s own scope — reconfiguring a live installation's
`health_check_url` stopped it from ever being probed again until
manually reactivated. Fixed to only advance status from the
pre-activation states; see `AI_MEMORY.md` for the full comparison
against `ConnectorService`'s own (correctly) unconditional equivalent.

---

## Tests

520 tests, **98.68%** branch coverage, against real PostgreSQL, Redis,
RabbitMQ, and MinIO.

```bash
uv run python -m pytest -q --cov=app --cov-report=term-missing
```

### `check_http_reachable` cannot be pointed at a test double

Builds its own internal `httpx.AsyncClient` (the same confirmed,
repo-wide limitation every prior AI-IOS service's own test suite
documents) — `PluginHealthService`'s own tests point at an
already-running container from the standing docker-compose stack
(RabbitMQ's own management UI) for "genuinely reachable," and a real
closed loopback port for "genuinely unreachable."

### `app/telemetry/tracing.py` has its own dedicated test file

Nothing in this build's own services or workers calls the `trace_*`
helpers yet (no call site was wired), so without a standalone
`tests/test_telemetry.py` the file would sit at 0% coverage. Mirrors
integration-hub-service's own `InMemorySpanExporter`-backed pattern —
a real `TracerProvider`, not a mock, so a future `attributes={...}`
regression (the confirmed repo-wide defect class this module's own
docstring warns about) would be caught for real.

---

## Notes worth keeping

- **All seven parallel test-writing agents hit an account-wide session
  limit mid-task this time**, not the usual one-or-two. Six worktrees
  survived with real partial progress and were committed and merged
  cleanly, including one genuine bug fix (the router-ordering hijack
  above) found by the publishers/marketplace-admin/health agent before
  it was cut off. The seventh (`test_api_plugins.py`/
  `test_api_installations.py`/`test_api_packages.py`) left no worktree
  at all — with the account-wide limit still active, redispatching a
  fresh agent would likely have failed identically, so those three
  files were written directly instead of waiting out the reset.
- **A real source bug in `StatisticsService.rollup()`**:
  `i.status.value` on `PluginInstallation.status` raised
  `AttributeError` on any window containing at least one installation
  — the column is backed by plain `String`, never a SQLAlchemy `Enum`
  type, so the ORM attribute is already a plain `str` at runtime, the
  same "enum-as-str" convention this service's own `app/models/enums.py`
  documents. Fixed to `str(i.status)`, matching the very next line's
  own `str(plugin.category)`.
- **Two test-authoring mistakes, not source bugs**: a hand-written
  `test_archive_plugin` forgot `Authorization` headers on its own
  `DELETE` call; a recovered agent's `test_generate_marketplace_report`
  keyed a dict by plugin `name` while both of its own test plugins
  shared the `make_plugin` fixture's default name, so the second
  silently clobbered the first before either assertion ran.
- **The `configure()` lifecycle bug** (see "Running it" above) —
  found live, not by any automated test, because no test in this
  suite happened to reconfigure an already-active installation and
  then check whether a *later* sweep tick still picked it up. A
  regression test now covers it directly at the service layer.

---

## What's deliberately out of scope

`shared_core.security.certificates` (X.509 validation/expiry/
fingerprinting) is available but unused — this service follows
`playbook-service`'s own raw-Ed25519-key-plus-fingerprint precedent for
publisher trust rather than a certificate chain, so there is no
certificate material anywhere in this build for it to validate. No
CRL/OCSP revocation checking exists anywhere in `shared_core`, and none
is built here either — a genuine gap, not yet needed without
certificates in the trust model. `ReportKind.PLUGIN_HEALTH`/
`.COMPATIBILITY`/`.SECURITY` return empty rows rather than a bespoke
builder each, the same "not every report kind needs a real builder in
the first cut" scope decision every prior AI-IOS service's own
`ReportService` has already made.
