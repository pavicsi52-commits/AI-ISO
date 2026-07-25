# Secrets Management Service

Centralized secret storage, envelope encryption, rotation, leasing,
certificate/SSH-key/API-key/token management, and audit for AI-IOS
([`docs/035_Enterprise_Secrets_Management_Service.md`](../../docs/035_Enterprise_Secrets_Management_Service.md)):
every component requiring credentials SHALL retrieve them from this
service, and secrets SHALL NEVER be stored in plaintext within any
business service. The sixth AI-IOS microservice built on
`packages/shared-core`, alongside `services/authentication-service`,
`services/user-management-service`, `services/rbac-service`,
`services/organization-service`, and `services/project-service`.

## Architecture

Standard service structure per
[`docs/008_Backend_Master_Architecture.md.txt`](../../docs/008_Backend_Master_Architecture.md.txt).
A few sub-packages specific to this service's domain:

- `app/encryption/envelope.py` — `EnvelopeEncryption`: master key wraps
  Data Encryption Keys (DEKs), DEKs encrypt secret values, built on
  `shared_core.security.encryption`'s AES-256-GCM primitives.
- `app/ssh/keygen.py` — RSA/ECDSA/Ed25519 keypair generation and
  `SHA256:...` fingerprinting (cross-checked against real
  `ssh-keygen -lf` output during live testing), built directly on
  `cryptography` since no `shared_core` equivalent exists.
- `app/certificates/importer.py` — thin wrapper over
  `shared_core.security.certificates` extracting the metadata a
  `certificate_store` row needs from an imported PEM certificate.
- `app/rotation/policy.py` / `app/leasing/policy.py` — pure,
  database-independent rotation-due and lease-expiration evaluation.
- `app/workers/` — `expiry_worker.py`/`lease_sweep_worker.py`: the
  actual check logic, driven by `background.py::run_periodic`'s
  lightweight in-process asyncio interval loop (not a queue consumer,
  not the full distributed `shared_core.scheduler` framework — see
  "Design decisions" below) and registered in `core/factory.py`'s
  lifespan.
- `app/telemetry/tracing.py` — secret access, encryption, decryption,
  rotation, lease operations, certificate validation, and provider-call
  spans.

### Design decisions worth knowing

- **Envelope encryption, DEKs minted per organization.** Master Key
  (a local file, `AIIOS_SECRETS_SERVICE_MASTER_KEY_PATH`, never
  persisted to the database — HSM/Cloud KMS integration is explicitly
  marked "(future)" in docs/035 itself, not a gap) wraps per-organization
  Data Encryption Keys, which in turn encrypt each
  `secret_versions.ciphertext` row with AES-256-GCM. DEKs are scoped
  per-organization rather than one shared key for the whole service
  because `organization_id` is a mandatory, non-nullable column on
  every AI-IOS entity table, and docs/035's own "Tenant isolation"
  requirement is best served by ensuring a compromised DEK for one
  organization can never expose another's secrets.
- **`GET /secrets/{id}` returns the decrypted value; `GET /secrets` and
  `GET /secrets/search` never do.** Docs/035's REST list has no
  separate "reveal" endpoint, and its own OBJECTIVE states other
  services retrieve credentials via this API — so the single-secret
  response is the one place plaintext appears. List/search views
  return metadata only, matching the "Never cache decrypted secrets" /
  "Caching of metadata only" split docs/035's own "PERFORMANCE" section
  draws.
- **Self-contained ACL, not a live RBAC call.** `SecretAccessGrant`
  (`secret_access` table) resolves docs/035's "Integrate with Prompt
  032 RBAC" instruction the same way `services/organization-service`
  and `services/project-service` resolved their own identical
  instructions: a secret's owner always has full access; anyone else
  needs an explicit, optionally-expiring grant naming the specific
  action (Read/Write/Rotate/Delete/Export/Share/Lease/Restore). The
  allow/deny decision itself lives in `app/api/deps.py`'s
  `require_secret_action`, not inside the service layer, mirroring
  `services/project-service`'s own `require_role_in_project` shape.
- **"Thin metadata table referencing the vault" pattern.**
  `certificate_store`, `ssh_key_store`, `api_key_store`, and
  `token_store` all store their *public* material in plaintext directly
  (certificates, public keys, key prefixes — genuinely not sensitive)
  and reference a `secret_vault` row via a `*_secret_id` foreign key for
  their actual sensitive private material. This gives one single source
  of truth (`Secret` + `SecretVersion` + `EncryptionKey`) for every kind
  of sensitive material this service manages, rather than four separate
  ad-hoc encryption implementations.
- **`token_store` has no REST surface.** Unlike certificates/SSH
  keys/API keys/providers, docs/035's REST list never names a
  `/tokens` endpoint — `TokenService` exists for programmatic
  completeness (the table is explicitly required) and is exercised
  directly in tests, the same "required table, no REST list entry"
  shape `services/project-service`'s own no-REST-surface sub-resources
  established.
- **Lightweight in-process scheduling, not the distributed framework.**
  Background expiry checks and lease sweeping use
  `app/workers/background.py::run_periodic` — a plain `asyncio.sleep`
  loop re-resolving fresh services on every tick — rather than
  `shared_core.scheduler`'s full leader-election/heartbeat/failover
  machinery, since this service doesn't yet run multi-replica
  deployments that would need leader election.
- **Zero plaintext persistence in the audit trail, no exception.**
  `SecretAuditEntry.before`/`after` capture metadata only (name,
  status, version *numbers*) — never a secret's plaintext or even its
  ciphertext. Verified by a dedicated test asserting the literal
  plaintext value never appears in any audit row after a read.

## Running Locally

```bash
uv sync
# Requires the repository root docker-compose stack running (Postgres,
# Redis, RabbitMQ) -- see the repository root README. This service also
# needs its own database created once:
#   docker exec aiios_postgres psql -U aiios -d postgres \
#     -c "CREATE DATABASE aiios_secrets OWNER aiios;"
# ...and a master key generated once:
#   uv run python -c "from shared_core.security.encryption import generate_encryption_key; print(generate_encryption_key())" > keys/master.key
uv run alembic upgrade head
uv run uvicorn main:app --reload --port 8006
```

Configuration is `AIIOS_`-prefixed environment variables via
`packages/shared-core/config` (see the repository root `.env.example`
for the shared `AIIOS_DATABASE_*`/`AIIOS_REDIS_*`/`AIIOS_RABBITMQ_*`
variables) plus this service's own `AIIOS_SECRETS_SERVICE_*` variables
(`app/config/settings.py`'s `SecretsServiceSettings`): `HOST`, `PORT`,
`CORS_ALLOWED_ORIGINS`, `JWT_PUBLIC_KEY_PATH`, `MASTER_KEY_PATH`,
`ROTATION_CHECK_INTERVAL_SECONDS`, `LEASE_SWEEP_INTERVAL_SECONDS`. Like
every downstream AI-IOS service, a missing JWT public key file is a
hard startup error — and, uniquely to this service, so is a missing
master key file.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET/POST /secrets`, `GET/PUT/DELETE /secrets/{id}` | Secret directory and lifecycle (`GET /{id}` includes the decrypted value) |
| `POST /secrets/{id}/rotate` | Manual rotation to a new value |
| `POST /secrets/{id}/lease` | Issue a temporary-credential lease |
| `DELETE /leases/{id}` | Revoke a lease |
| `GET /secrets/search` | Full-text search, filtering, sorting, pagination |
| `GET/POST /certificates`, `DELETE /certificates/{id}` | Certificate store (TLS/Client/CA) |
| `GET/POST /ssh-keys`, `DELETE /ssh-keys/{id}` | SSH key generation/import |
| `GET/POST /api-keys`, `DELETE /api-keys/{id}` | Managed third-party API keys |
| `GET/POST /providers` | External secret provider configuration |
| `GET /health` / `/readiness` / `/liveness` | Health checks |
| `GET /metrics` | Prometheus metrics |
| `GET /docs` / `/openapi.json` | OpenAPI documentation |

Every mutating endpoint on a specific secret (`GET/PUT/DELETE
/secrets/{id}`, `/rotate`, `/lease`) is gated by
`require_secret_action`: the secret's owner always passes; anyone else
needs a matching, non-expired `SecretAccessGrant`. `POST /secrets`,
list/search, and every certificate/SSH-key/API-key/provider endpoint
require valid authentication only.

## Testing

```bash
uv run pytest --cov=app --cov-report=term-missing
```

188 tests, 97.61% coverage, entirely against real infrastructure (the
repository root's docker-compose Postgres/Redis/RabbitMQ) and real
AES-256-GCM encryption — no mocked database, no mocked crypto.
Postgres isolation between tests uses a per-test SAVEPOINT
(`join_transaction_mode="create_savepoint"` — see `tests/conftest.py`),
the same pattern every prior AI-IOS service established. Dedicated
coverage includes: encryption round-trips, wrong-key/tampered-ciphertext
rejection (`InvalidTag`), key rotation and DEK re-encryption, SSH
fingerprints cross-checked against real `ssh-keygen -lf` output, real
self-signed X.509 certificate parsing, the full REST lifecycle
including access-control enforcement (owner/grantee/stranger), and an
explicit assertion that no audit entry ever contains a secret's
plaintext value.

## Docker

Build from the **repository root** (this service is a uv workspace
member and its lockfile resolves against the whole workspace):

```bash
docker build -f services/secrets-management-service/Dockerfile -t aiios/secrets-management-service .
```

Built and health-checked live against the real docker-compose network
(`aiios_aiios_network`) — `docker ps` reports `(healthy)`, and
`/health`/`/readiness` confirm genuine Postgres/Redis connectivity from
inside the container.

## Real bugs found via live smoke-testing

Per this repository's "start the real service and exercise it" testing
discipline, found *before* the automated test suite was written, then
covered by dedicated regression tests:

1. **Tags silently dropped from `PUT`/`POST .../rotate` responses.**
   `secret_to_summary()` defaulted to an empty tag list unless the
   caller explicitly fetched and passed them in — `create_secret`
   passed the request body's own tags, but `update_secret` and
   `rotate_secret` didn't fetch the secret's actual tags at all, so a
   tagged secret appeared to have lost its tags in those two responses
   even though the underlying `secret_tags` rows were untouched. Fixed
   by fetching current tags via `SecretTagService` in both handlers.
2. **`SecretService.update()` crashed on a freshly-reloaded secret.**
   `secret.status.value` assumed `secret.status` is always a
   `SecretStatus` enum instance, but SQLAlchemy's identity map holds
   *weak* references — once the `Secret` object returned by `create()`
   fell out of scope at the end of that request, Python's garbage
   collector reclaimed it, and a later `PUT` request's fresh `SELECT`
   returned the column's raw `String` value (this column, like every
   enum-typed column across every AI-IOS service, is stored as a plain
   `String`, not `sqlalchemy.Enum` — relying on `StrEnum`'s value-based
   equality for comparisons, which silently tolerates the mismatch
   everywhere except an explicit `.value` access). Reproduced
   deterministically via a live two-request `POST` then `PUT` sequence,
   not a rare race. Fixed by using `str(secret.status)` instead of
   `.value` — identical result whichever shape the attribute is
   currently in, since `SecretStatus` is a `StrEnum`.
3. **`POST /secrets`, `GET /secrets`, `GET /secrets/search`, and every
   endpoint in `certificate.py`/`ssh_key.py`/`api_key.py`/`provider.py`
   had no authentication requirement at all** — despite `create_secret`'s
   own docstring already claiming "requires only authentication."
   `require_secret_action` only applies to endpoints naming a specific
   existing secret (`GET/PUT/DELETE /secrets/{id}`, `/rotate`,
   `/lease`), so every endpoint that doesn't reference an existing
   secret was left with zero `Depends` at all. Found via a live
   `test_create_secret_requires_auth` integration test expecting `401`
   and getting `201` instead. Fixed by adding a `CurrentUserId`
   dependency to all thirteen affected endpoints.

Every other mechanism — real AES-256-GCM encryption at rest (verified
by querying `secret_versions.ciphertext` directly in Postgres and
confirming it is never the plaintext), decrypt round-trips, manual
rotation with version history preserved, lease issue/revoke, real
self-signed certificate import with fingerprint/subject/issuer
extraction, SSH keypair generation with fingerprints matching real
`ssh-keygen -lf` output byte-for-byte, API key generation, provider
registration, tenant isolation, and the self-contained ACL (owner
always allowed, stranger denied with `403`, granted principal
allowed) — was verified end-to-end via live `curl` against a running
`uvicorn` instance before the automated test suite was written, and
found no further defects.
