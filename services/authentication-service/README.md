# Authentication Service

Identity verification and session management for AI-IOS
([`docs/030_Enterprise_Authentication_Service.md.txt`](../../docs/030_Enterprise_Authentication_Service.md.txt)):
registration, email verification, password-based login with optional
TOTP MFA, JWT access/refresh tokens, Redis-backed sessions, account
lockout, password reset, trusted devices, personal API keys, and
service accounts. The first AI-IOS microservice built on
`packages/shared-core` — it owns its own database, Alembic migrations,
and REST API, rather than being a shared library another service
imports.

**Scope note**: per this prompt's own "DO NOT IMPLEMENT" list and a
scope decision confirmed with the user before implementation began,
OAuth2/OIDC, SAML, LDAP/Active Directory federation, and multi-tenant
Organization management are deferred to a follow-up phase. Core
username+password authentication, TOTP MFA, JWT, sessions, API keys,
and service accounts are fully implemented now.

## Architecture

Standard service structure per
[`docs/008_Backend_Master_Architecture.md.txt`](../../docs/008_Backend_Master_Architecture.md.txt):
`app/{api,core,config,models,repositories,schemas,services,audit,events,telemetry,middleware}`,
`alembic/` (this service's own migrations — per
`shared_core.database.migration`'s own docstring, "this package owns
no business schema... each service owns its own Alembic
script_location"), `main.py`, `tests/`.

Every reusable primitive comes from `packages/shared-core` rather than
being reimplemented: JWT RS256 encode/decode and refresh-token pairs
(`shared_core.security.jwt`/`.refresh`), Argon2 password hashing and
policy (`shared_core.security.password`), TOTP + recovery codes
(`shared_core.security.mfa`), Redis-backed sessions
(`shared_core.security.sessions.SessionManager`), API key generation/
hashing (`shared_core.security.apikey`), the generic async repository
and Unit-of-Work session lifecycle (`shared_core.database`), and
security/structured audit logging (`shared_core.security.audit`).
This service's own code is the *business orchestration* on top —
`app/services/authentication.py`'s `AuthenticationService` is the
central orchestrator tying registration, login, MFA, lockout, device
tracking, sessions, tokens, audit, notifications, and domain events
together into one coherent flow per request.

### Design decisions worth knowing

- **`DEFAULT_ORGANIZATION_ID`** (`app/constants.py`): every entity
  inheriting `shared_core.database.base.BaseModel` carries a mandatory
  (non-nullable) `organization_id`, but this prompt explicitly excludes
  Organizations and no Organization service exists yet to mint real
  ones. A fixed, documented placeholder UUID is used instead — safe
  because the column is a bare UUID with no foreign key, per
  `BaseEntityMixin`'s own cross-service-safe design, so it needs no
  real row to reference and can be replaced service-wide later without
  a migration.
- **Dual-track sessions and audit**: `shared_core.security.sessions
  .SessionManager` (Redis) is the fast, per-request source of truth for
  "is this session currently valid right now"; this service's own
  `sessions` Postgres table (`SessionRepository`) is the durable,
  listable, auditable record `GET /auth/sessions` reads. The same
  pattern applies to audit: `shared_core.security.audit
  .audit_security_event` for SIEM-shaped structured logging, plus this
  service's own `authentication_audit` table for a durable, queryable
  trail (`app/audit/audit.py`'s `AuditService` writes both).
- **Token tracking, not token storage**: JWTs are stateless and
  self-contained and are never persisted. Only the `jti` claim plus
  enough metadata to answer "has this been revoked?" is tracked, in
  `access_tokens`/`refresh_tokens` — `TokenService` wraps
  `shared_core.security.jwt`/`.refresh` (which explicitly own no
  storage) with this service's own revocation/blacklist bookkeeping.
- **`LoginResult`**: `AuthenticationService.login()` returns a frozen
  dataclass (`tokens`, `user`, `mfa_challenge_id`, and a
  `requires_mfa` property) instead of a union/tuple-or-string, to
  cleanly express "either issued tokens, or an MFA challenge requiring
  the client to resubmit the same login request with `mfa_code`
  filled in." `mfa_challenge_id` is UX correlation only, not a
  security boundary — the password is re-verified on the follow-up
  call regardless, so no separate challenge-store subsystem exists.
- **MFA enrollment is "mark now, wire later"**: `POST /auth/mfa/enable`
  creates an unverified TOTP device (`is_primary=True` immediately,
  `is_verified=False`); only `POST /auth/mfa/verify` (via
  `MfaService.confirm_enrollment()`) enforces it at login.
- **An inactive account looks identical to an unknown one at login**:
  `UserRepository.get_by_email()` already excludes soft-deleted
  (`is_active=False`) users by default, so `login()` has no separate
  "account is inactive" branch — it never reaches one. This is
  deliberate: it keeps account status from leaking to an
  unauthenticated caller, and an earlier version's dead `is_active`
  check (unreachable given that filtering) was removed once test
  coverage surfaced it.
- **Notifications are best-effort everywhere**: `AuthNotificationService`
  catches `shared_core.exceptions.notification.NotificationError` in
  one private `_send()` helper every public method routes through, so
  no caller (registration, password reset, login alerts, ...) needs to
  individually guard against email delivery being unavailable — a real
  bug found via live smoke-testing this service against a docker-compose
  environment with no SMTP configured (see below).

## Running Locally

```bash
uv sync
# Requires the repository root docker-compose stack running (Postgres,
# Redis, RabbitMQ) -- see the repository root README.
uv run alembic upgrade head
uv run uvicorn main:app --reload --port 8001
```

Configuration is `AIIOS_`-prefixed environment variables via
`packages/shared-core/config` (see the repository root `.env.example`
for the shared `AIIOS_DATABASE_*`/`AIIOS_REDIS_*`/`AIIOS_RABBITMQ_*`
variables) plus this service's own `AIIOS_AUTH_SERVICE_*` variables
(`app/config/settings.py`'s `AuthServiceSettings`): `HOST`, `PORT`,
`CORS_ALLOWED_ORIGINS`, `JWT_PRIVATE_KEY_PATH`, `JWT_PUBLIC_KEY_PATH`.
If no JWT keypair exists at the configured paths, one is generated and
persisted automatically on first startup (`app/config/keys.py`) —
convenient for local development; a real deployment provisions real
key files ahead of time so restarts and multi-instance deployments
share one signing identity.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `POST /auth/register` | Create a user with a password credential |
| `POST /auth/login` | Authenticate; may return an MFA challenge |
| `POST /auth/refresh` | Rotate a refresh token |
| `POST /auth/logout` | Revoke a refresh token and terminate its session |
| `POST /auth/forgot-password` / `reset-password` | Password reset flow |
| `POST /auth/verify-email` / `resend-verification` | Email verification flow |
| `POST /auth/mfa/enable` / `verify` / `disable` | TOTP MFA lifecycle |
| `GET /auth/profile` | The authenticated caller's own profile |
| `GET/DELETE /auth/sessions{,/{id}}` | List / terminate sessions |
| `GET/DELETE /auth/devices{,/{id}}` | List / revoke trusted devices |
| `POST/GET/DELETE /auth/apikeys{,/{id}}` | Personal API key lifecycle |
| `GET /health` / `/readiness` / `/liveness` | Health checks |
| `GET /metrics` | Prometheus metrics |
| `GET /docs` / `/openapi.json` | OpenAPI documentation |

Service accounts (`app/services/service_accounts.py`) have a complete
service and repository layer but no REST surface yet — machine
identities are provisioned out-of-band, not via public self-service
endpoints, matching the same reasoning as the deferred-federation scope
note above.

## Testing

```bash
uv run pytest --cov=app --cov-report=term-missing
```

179 tests, 99.75% coverage, entirely against real infrastructure
(the repository root's docker-compose Postgres/Redis/RabbitMQ) — no
mocked database. Postgres isolation between tests uses a per-test
SAVEPOINT (`join_transaction_mode="create_savepoint"` — see
`tests/conftest.py`), not a second database: every `BaseRepository`
write only `flush()`es, so an outer, always-rolled-back transaction
safely contains everything a test does, including a real
`session.commit()` reached through the app's own HTTP layer.
`tests/test_persistence_regression.py` deliberately bypasses that
isolation (`real_client`, no dependency override) to verify a write in
one request is durably visible to a genuinely separate later request,
with explicit cleanup — the exact regression this package's own
development caught (see below).

## Docker

Build from the **repository root** (this service is a uv workspace
member and its lockfile resolves against the whole workspace):

```bash
docker build -f services/authentication-service/Dockerfile -t aiios/authentication-service .
```

## Real bugs found via live smoke-testing

Per this repository's "start the real service and exercise it" testing
discipline, three real bugs were caught by actually running `uvicorn`
against the real docker-compose stack and driving it with `curl` —
none would have been caught by a test suite using a single shared
in-memory session:

1. **Registration was blocked entirely by a welcome-email failure.**
   `EmailSettings.email_enabled=False` by default in this dev
   environment means zero notification channels are registered, so
   `NotificationManager.send()` raised `ChannelUnavailableError`
   straight out of `register()`. Fixed by making every
   `AuthNotificationService` method best-effort (see "Design decisions"
   above) rather than requiring every caller to guard individually.
2. **A user registered in one request was invisible to a login in the
   next.** `get_db_session` originally never committed —
   `BaseRepository.create()`/`update()` only ever `flush()`, by design
   (Unit of Work owns the commit boundary, not the repository). Fixed
   by routing `get_db_session` through
   `shared_core.database.session.session_scope`, which commits on a
   clean request and rolls back on an exception.
3. **Login failed with `AIIOS-EVENT-0002` ("Event 'UserLoggedIn' is not
   registered")** the first time it tried to publish a domain event.
   `app/events/auth_events.py`'s 14 event classes were defined but
   never registered with `shared_core.events.registry.default_registry`
   — fixed by decorating each with `@default_registry.register`.

## Troubleshooting

- **`ModuleNotFoundError: email_validator`**: `pydantic[email]` extra;
  confirm it installed (`uv sync`) rather than plain `pydantic`.
- **RabbitMQ `AMQPInternalError` on connect (Windows/Git Bash)**: the
  MSYS2 path-conversion layer can silently mangle a vhost value like
  `/aiios` passed as an inline shell env var into a Windows path. Either
  omit `AIIOS_RABBITMQ_VHOST` (the Python-side default is already
  `/aiios`) or prefix the command with `MSYS_NO_PATHCONV=1`.
- **`/readiness` reports a failed Redis check**: this service's Redis
  requires a password in this environment (`AIIOS_REDIS_PASSWORD`) —
  a bare `redis-cli ping` against the container returns `NOAUTH`.
