"""Authentication and authorization.

Every prior AI-IOS service with a "docs prompt says integrate Prompt 032
RBAC/Prompt 050 Policy Engine" instruction chose local, self-contained
enforcement over a live per-request HTTP call to
``services/rbac-service``/``services/policy-engine-service`` (confirmed
during this prompt's own research phase, across
``secrets-management-service``, ``project-service``, and
``organization-service``, each of which documents the same reasoning
directly in its own code) -- this service follows the same precedent,
using `shared_core.security.rbac`/`.authorization` directly against a
caller's own decoded JWT claims, rather than introducing this
monorepo's first live cross-service authorization call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from shared_core.enums.permission import Permission
from shared_core.enums.role import Role
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.security.authorization import AuthorizationResult, authorize
from shared_core.security.jwt import decode_token

from app.models.enums import AuthenticationMethod
from app.services.apikey import ApiKeyService


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Who is making this call, and how they proved it."""

    method: AuthenticationMethod
    subject_id: str | None
    role: Role | None = None
    scopes: frozenset[str] = field(default_factory=frozenset)
    client_id: UUID | None = None
    organization_id: UUID | None = None
    """The organization the caller's own JWT claims them as belonging
    to -- may differ from the organization a request targets, which is
    exactly the case "Organization Isolation" (docs/056) exists to
    catch."""


class AuthService:
    """Authenticates callers and authorizes their requests."""

    def __init__(self, *, api_keys: ApiKeyService, jwt_public_key: str) -> None:
        self._api_keys = api_keys
        self._jwt_public_key = jwt_public_key

    async def authenticate_jwt(self, token: str) -> AuthContext:
        """Authenticate a caller via a Bearer JWT.

        Raises:
            AuthenticationError: If the token is missing, malformed, expired, or invalid.
        """
        claims = decode_token(token, public_key=self._jwt_public_key)
        role_value = claims.get("role")
        organization_value = claims.get("organization_id")
        return AuthContext(
            method=AuthenticationMethod.JWT,
            subject_id=str(claims["sub"]),
            role=Role(role_value) if role_value else None,
            scopes=frozenset(claims.get("scopes", [])),
            organization_id=UUID(str(organization_value)) if organization_value else None,
        )

    async def authenticate_api_key(self, raw_key: str, *, source_ip: str | None = None) -> AuthContext:
        """Authenticate a caller via an API key.

        Raises:
            AuthenticationError: If the key is invalid, expired, revoked, or IP-restricted.
        """
        stored = await self._api_keys.verify(raw_key, source_ip=source_ip)
        return AuthContext(
            method=AuthenticationMethod.API_KEY,
            subject_id=str(stored.id),
            scopes=frozenset(stored.scopes),
            client_id=stored.client_id,
            organization_id=stored.organization_id,
        )

    def authenticate_anonymous(self) -> AuthContext:
        """The context for a route that permits unauthenticated access."""
        return AuthContext(method=AuthenticationMethod.ANONYMOUS, subject_id=None)

    def authorize_request(
        self,
        context: AuthContext,
        *,
        target_organization_id: UUID,
        required_permission: Permission | None,
        required_scopes: list[str] | None = None,
    ) -> AuthorizationResult:
        """Whether *context* is authorized for a request targeting *target_organization_id*.

        Checks, in order: organization isolation (the caller's own JWT
        organization must match the request's target, unless the caller
        authenticated via an API key scoped to that same organization
        already), required scopes (for API-key callers), then RBAC.
        """
        if (
            context.organization_id is not None
            and context.organization_id != target_organization_id
        ):
            return AuthorizationResult(
                granted=False, reason="Caller's organization does not match the request's target."
            )
        if required_scopes:
            missing = [scope for scope in required_scopes if scope not in context.scopes]
            if missing:
                return AuthorizationResult(granted=False, reason=f"Missing scopes: {missing}")
        if required_permission is None:
            return AuthorizationResult(granted=True, reason="No permission required.")
        if context.role is None:
            return AuthorizationResult(granted=False, reason="No role available to authorize.")
        return authorize(role=context.role, permission=required_permission)


__all__ = ["AuthContext", "AuthService"]
