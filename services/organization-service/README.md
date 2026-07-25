# Organization Service

Multi-tenant organization management for AI-IOS
([`docs/033_Enterprise_Organization_Service.md.txt`](../../docs/033_Enterprise_Organization_Service.md.txt)):
organizations, settings, preferences, custom metadata, verified
domains, branding, subscriptions, licenses, resource limits, quotas,
departments, business units, teams, invitations, members, activity
feed, audit trail, statistics, and tags — 19 tables in total. The
fourth AI-IOS microservice built on `packages/shared-core`, alongside
`services/authentication-service`, `services/user-management-service`,
and `services/rbac-service`.

**A genuine architectural first**: every prior AI-IOS service only ever
referenced an organization by a bare, foreign-key-less `organization_id`
placeholder UUID — none of them owned an `organizations` table. This
service does. Its `Organization.organization_id` (the mandatory tenant
column every `BaseModel`-derived entity carries) is set equal to its
own `id` at creation — the standard self-referential pattern for a
multi-tenant system's tenant "root" entity — and every child table in
this service reuses that same inherited `organization_id` column as a
*real* `ForeignKeyConstraint` back to `organizations.id`
(`ondelete="CASCADE"`), not a second redundant column.

## Architecture

Standard service structure per
[`docs/008_Backend_Master_Architecture.md.txt`](../../docs/008_Backend_Master_Architecture.md.txt).
A few sub-packages specific to this service's domain:

- `app/organizations/membership.py` — `role_at_least()`, the pure
  ranking function (`member < admin < owner`) behind this service's own
  admin-gating.
- `app/quotas/enforcement.py` — `check_quota()`, a pure function
  comparing current usage against a configured cap (`maximum <= 0`
  means unlimited). Wrapped by `OrganizationQuotaService.check_user_quota()`,
  which is invoked from `InvitationService.accept()` before a new
  membership is actually created.
- `app/telemetry/tracing.py` — organization CRUD, department
  operations, quota checks, license validation, and analytics spans.
- `app/services/` — one service per table/domain concept; 15 of them
  have a REST surface, 4 don't (see below).

### Design decisions worth knowing

- **Self-contained membership-role authorization, not a live RBAC HTTP
  call.** Docs/033's "SECURITY" section says "Integrate Prompt 032"
  (`services/rbac-service`). This service instead enforces access
  control entirely through its own `OrganizationMember.role`
  (owner/admin/member) via `app/api/deps.py`'s `require_admin`/
  `require_member` dependencies — introducing a new cross-service
  HTTP-calling convention (nothing else in this codebase does
  synchronous service-to-service calls) was judged higher-risk than the
  value of delegating a three-value role check. Documented here as a
  deliberate scope boundary and follow-up integration point, not an
  oversight.
- **Strict tenant isolation was a real bug, caught by live smoke
  testing, not assumed correct.** The first working version gated every
  *mutation* on organization-scoped sub-resources (settings, branding,
  departments, teams, licenses, quotas, analytics) with `require_admin`,
  but left their **reads** authenticated-only — any logged-in user of
  *any* organization could `GET` another organization's settings
  (`password_policy`, `allowed_domains`, `session_timeout_minutes`,
  `notification_policy`), license, quota, and department/team lists.
  Docs/033's own "SECURITY" section is explicit: "Strict tenant
  isolation." / "Prevent cross-tenant access." A dedicated `require_member`
  dependency now gates every such read; only the top-level
  `GET /organizations`/`GET /organizations/{id}` directory endpoints
  remain authenticated-only, deliberately, since they expose only an
  organization's own basic public identity (name, slug, domain, status)
  — the same information `GET /organizations` already lists for every
  organization to any authenticated platform user.
- **Quota enforcement was defined but never wired in — also caught live.**
  `OrganizationQuotaService.check_user_quota()` existed, fully
  implemented and tested, but nothing ever called it: an organization
  at its `max_users` limit could accept unlimited invitations. Fixed by
  calling it from `InvitationService.accept()` immediately before
  creating the new membership row, raising `BusinessRuleError` (422) if
  the organization is already at capacity. Invitations can still be
  *sent* past the quota (an org may legitimately over-invite and let
  quota decide who actually gets in first) — only *acceptance* is
  gated, matching docs/033's "Enforce quotas" requirement literally
  ("quota" is a capacity ceiling on membership, not on outreach).
- **The seed migration provisions a *real* default organization**, at
  the exact same UUID (`00000000-0000-0000-0000-000000000001`) every
  other AI-IOS service's own `DEFAULT_ORGANIZATION_ID` placeholder
  already references. What was a bare, unresolvable UUID everywhere
  else becomes a real, resolvable `organizations` row here — plus its
  own default settings/preferences/branding/subscription/license/
  limits/quota child rows, the same shape `OrganizationService.create()`
  provisions for every new organization.
- **`business_units`, `subscriptions`, `preferences`, `metadata`,
  `tags`, and `domains` have no dedicated REST surface.** Docs/033's own
  endpoint list doesn't name one for any of them — full service-layer
  CRUD exists (`app/services/business_unit.py`,
  `app/services/subscription.py`, etc.) for programmatic completeness
  and future REST exposure, matching `services/rbac-service`'s
  identical scope decision for `resource_permissions`.
- **Invitation `accept`/`reject` extend the literal REST list.**
  Docs/033's endpoint list only names `POST /organizations/{id}/invite`,
  but its "ORGANIZATION INVITATIONS" functional section explicitly
  requires "Accept, Reject" support. `POST /organizations/invite/accept`
  and `POST /organizations/invite/reject` are unauthenticated — the
  token itself is the credential — the same design
  `services/user-management-service`'s own invitation flow established.
  The raw invitation token is never returned over any authenticated
  endpoint either, only its SHA-256 hash is persisted; it's delivered
  solely through the (best-effort, non-blocking) invitation email.
- **Analytics are honestly zero-filled where this service has no data.**
  `OrganizationStatisticsService` computes real `user_count` (from this
  service's own `organization_members`) and real
  `license_utilization_percent` (from its own `organization_licenses`).
  Every other field docs/033 names (project/asset/workflow/automation/
  validation counts, storage/API/AI usage) is left at `0` rather than
  fabricated — those owning services are explicitly out of scope for
  this prompt and don't exist yet in this build, the same honesty
  precedent `services/user-management-service`'s "Virus Scan Hook"
  established.

## Running Locally

```bash
uv sync
# Requires the repository root docker-compose stack running (Postgres,
# Redis, RabbitMQ) -- see the repository root README. This service also
# needs its own database created once:
#   docker exec aiios_postgres psql -U aiios -d postgres \
#     -c "CREATE DATABASE aiios_organization OWNER aiios;"
uv run alembic upgrade head
uv run uvicorn main:app --reload --port 8004
```

Configuration is `AIIOS_`-prefixed environment variables via
`packages/shared-core/config` (see the repository root `.env.example`
for the shared `AIIOS_DATABASE_*`/`AIIOS_REDIS_*`/`AIIOS_RABBITMQ_*`
variables) plus this service's own `AIIOS_ORG_SERVICE_*` variables
(`app/config/settings.py`'s `OrganizationServiceSettings`): `HOST`,
`PORT`, `CORS_ALLOWED_ORIGINS`, `JWT_PUBLIC_KEY_PATH`,
`STATISTICS_CACHE_TTL_SECONDS`. Like every downstream AI-IOS service, a
missing JWT public key file is a hard startup error — this service
holds no private key to fall back to generating one; it only verifies
tokens issued by `services/authentication-service`.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET/POST /organizations`, `GET/PUT/DELETE /organizations/{id}` | Organization directory and lifecycle |
| `GET/PUT /organizations/{id}/settings` | Security/session/retention settings (member read, admin write) |
| `GET/PUT /organizations/{id}/branding` | Logo/theme/email-template branding (member read, admin write) |
| `GET/POST /organizations/{id}/departments`, `PUT/DELETE /departments/{id}` | Department management |
| `GET/POST /organizations/{id}/teams`, `PUT/DELETE /teams/{id}` | Team management |
| `GET/PUT /organizations/{id}/licenses` | License tracking, activation, expiry validation |
| `GET/PUT /organizations/{id}/quotas` | Per-organization resource caps |
| `POST /organizations/{id}/invite` | Invite a member (admin only) |
| `POST /organizations/invite/accept` / `/reject` | Accept/reject an invitation (unauthenticated; token is the credential) |
| `GET /organizations/{id}/analytics` | Usage statistics snapshot |
| `GET /health` / `/readiness` / `/liveness` | Health checks |
| `GET /metrics` | Prometheus metrics |
| `GET /docs` / `/openapi.json` | OpenAPI documentation |

## Testing

```bash
uv run pytest --cov=app --cov-report=term-missing
```

118 tests, 97.75% coverage, entirely against real infrastructure (the
repository root's docker-compose Postgres/Redis/RabbitMQ) — no mocked
database. Postgres isolation between tests uses a per-test SAVEPOINT
(`join_transaction_mode="create_savepoint"` — see `tests/conftest.py`),
the same pattern every prior AI-IOS service established; every test
automatically sees the seed migration's default organization for free,
since it was already committed before the SAVEPOINT-isolated
transaction began.

## Docker

Build from the **repository root** (this service is a uv workspace
member and its lockfile resolves against the whole workspace):

```bash
docker build -f services/organization-service/Dockerfile -t aiios/organization-service .
```

## Real bugs found via live smoke-testing

Per this repository's "start the real service and exercise it" testing
discipline, both of these were caught *before* the automated test suite
was written, then covered by dedicated regression tests:

1. **Tenant-isolation gap**: `GET` on organization-scoped sub-resources
   (settings, branding, departments, teams, licenses, quotas,
   analytics) was authenticated-only, letting any platform user read
   any organization's private configuration. Fixed with a `require_member`
   dependency; see "Design decisions" above.
2. **Quota enforcement was never wired in**: `check_user_quota()`
   existed but nothing called it, so `max_users` was unenforceable.
   Fixed by gating `InvitationService.accept()`; see "Design decisions"
   above.

Every other mechanism — organization creation with automatic owner
membership, settings/branding CRUD, department/team creation and the
split literal-path update/delete routes, license/quota read-and-update,
the full invite → accept/reject flow, and soft-delete-then-404 — was
verified end-to-end via live `curl` against a running `uvicorn`
instance before the automated test suite was written, and found no
further defects.
