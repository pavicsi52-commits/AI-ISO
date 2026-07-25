# Enterprise Security Framework

Everything security-related lives inside this package. No microservice
implements custom security.

## Security Guide

Security principles (docs/017 "SECURITY PRINCIPLES") are structural, not
just documented intent:

- **Deny by default** -- `PolicyEngine.evaluate()` denies any action with
  no registered policy; RBAC's `has_permission()` returns `False` for
  anything not explicitly granted.
- **Secure by default** -- `production_headers()`/`production_cors_config()`
  are the strict defaults; a service has to explicitly opt into
  `development_headers()`/`development_cors_config()`.
- **No anonymous privileged access** -- every `@requires_*` decorator
  raises `AuthenticationError`/`AuthorizationError` rather than silently
  proceeding when `SecurityContext` isn't populated.

## RBAC Guide

```python
from shared_core.security import Role, Permission, has_permission, has_scoped_permission, PermissionScope

has_permission(Role.OPERATOR, Permission.CREATE)  # role -> permission

has_scoped_permission(  # role AND tenant scope
    Role.ORGANIZATION_ADMIN, Permission.UPDATE,
    scope=PermissionScope.ORGANIZATION,
    resource_organization_id=resource.organization_id,
    context_organization_id=caller.organization_id,
)
```

Custom, inherited roles (`shared_core.security.roles.CustomRole`) resolve
down to the same `Permission` set RBAC checks against. Resource ownership
beyond role (`shared_core.security.permissions.can_access_resource`) and
attribute-based policies (`shared_core.security.policies.PolicyEngine`)
layer on top -- see `shared_core.security.authorization.authorize()` for
how all three combine.

## JWT Guide

```python
from shared_core.security import encode_token, decode_token, KeyRing

token = encode_token({"sub": str(user_id)}, private_key=private_key, algorithm="RS256")
claims = decode_token(token, public_key=public_key)  # RS256 or ES256, 30s clock-skew leeway
```

Key rotation: register both the outgoing and incoming public keys in a
`KeyRing`, sign new tokens with the new key's `kid`, and old in-flight
tokens keep verifying until they expire naturally. Revocation: pass
`is_revoked=your_lookup_fn` to `decode_token()` -- checked against the
token's `jti`. Refresh tokens: `shared_core.security.refresh.issue_token_pair()`
/ `rotate_token_pair()`.

## MFA Guide

```python
from shared_core.security import generate_totp_secret, generate_totp_code, verify_totp_code, generate_recovery_codes

secret = generate_totp_secret()  # show as a QR code to the user once
verify_totp_code(secret, user_submitted_code)  # +/-30s clock drift tolerated
recovery_codes = generate_recovery_codes()  # show once, store hashed
```

TOTP implements RFC 6238 directly (no new dependency). Email OTP and
trusted-device tokens are also provided; WebAuthn/FIDO2 are future work.

## Secret Management Guide

```python
from shared_core.security import resolve_secret, mask_secret

resolve_secret("AIIOS_DATABASE_PASSWORD")  # env var -> Docker secret -> Kubernetes secret
mask_secret(value)  # for safe display in logs/UIs
```

Vault, AWS Secrets Manager, Azure Key Vault, and GCP Secret Manager are
explicitly future backends (docs/017 "SECRET MANAGEMENT").

## Developer Guide

### Decorators

```python
from shared_core.security.decorators import requires_auth, requires_role, requires_permission, requires_mfa

@requires_auth()
@requires_permission(Permission.DELETE)
async def delete_project(project_id: UUID) -> None: ...
```

All seven (`requires_auth`, `requires_role`, `requires_permission`,
`requires_api_key`, `requires_organization`, `requires_project`,
`requires_mfa`) read `shared_core.security.context.SecurityContext`,
which a service's authentication middleware
(`shared_core.security.middleware.JwtAuthenticationMiddleware`) populates
per request.

### Sessions (Redis-backed)

```python
from shared_core.security.sessions import SessionManager

manager = SessionManager(cache_manager)  # shared_core.cache.CacheManager
session = await manager.create_session(user_id=str(user.id))
await manager.validate_session(session.session_id)  # idle + absolute timeout enforced
```

### Rate limiting (distributed)

```python
from shared_core.security.ratelimit import DistributedRateLimiter, rate_limit_key

limiter = DistributedRateLimiter(cache_manager, max_requests=100, window_seconds=60)
await limiter.allow(rate_limit_key(scope="user", identifier=str(user.id)))
```

Single-replica deployments can keep using
`shared_core.middleware.rate_limit.InMemoryRateLimiter` (Prompt 012); this
is for when limits must be shared across processes.

### Security audit logging

```python
from shared_core.security.audit import SecurityAuditEventType, audit_security_event

audit_security_event(SecurityAuditEventType.FAILED_LOGIN, actor_id=str(user_id), ip=request.client.host)
```

Every event type docs/017 "SECURITY AUDIT" lists flows through
`shared_core.logging`'s `.security()` method with a stable, structured
shape.

## Architecture Notes

- **No circular imports**: `shared_core.security` and
  `shared_core.validation` (Prompt 016) depend on each other in only one
  direction (`validation` -> `security`); `security/validators/` exists
  specifically so this package never needs to import `shared_core.validation`
  back.
- **Package renames from Prompt 012**: `jwt.py`, `password.py`, `rbac.py`,
  `encryption.py`, `secrets.py` became packages of the same name (same
  import path, more content). `tokens.py` was renamed to `apikey/` to
  match this prompt's directory structure -- that's the one import path
  that changed.
- **Sessions and rate limiting are Redis-backed** via
  `shared_core.cache.manager.CacheManager` (Prompt 012's baseline cache
  client) rather than waiting for Prompt 019's fuller Cache Framework --
  the basic `get`/`set`/`delete` primitives already there are sufficient.
