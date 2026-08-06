"""AuthService: JWT/API-key authentication and RBAC authorization.

Against a real, session-scoped RSA keypair for JWTs (``tests/conftest
.py``'s ``jwt_keypair``) and real PostgreSQL-backed API keys -- no
mocking: every JWT here is genuinely signed and verified through
``shared_core.security.jwt``, and every API key genuinely persisted and
looked up through ``ApiKeyService``.
"""

from __future__ import annotations

import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from shared_core.enums.permission import Permission
from shared_core.enums.role import Role
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.security.jwt import encode_token

from app.models.enums import AuthenticationMethod
from app.services.auth import AuthContext, AuthService


def _token(private_key: str, **claims: object) -> str:
    """A real, signed JWT with sensible default claims, overridable per test."""
    base: dict[str, object] = {"sub": str(uuid.uuid4()), "role": "super_admin", "scopes": []}
    base.update(claims)
    return encode_token(base, private_key=private_key)  # type: ignore[arg-type]


class TestAuthenticateJwt:
    async def test_a_valid_token_produces_a_context_with_every_claim(
        self, auth_service: AuthService, jwt_keypair, organization_id
    ) -> None:
        private_key, _public_key = jwt_keypair
        user_id = uuid.uuid4()
        token = _token(
            private_key,
            sub=str(user_id),
            role="operator",
            scopes=["gateway:read", "gateway:write"],
            organization_id=str(organization_id),
        )

        context = await auth_service.authenticate_jwt(token)

        assert context.method == AuthenticationMethod.JWT
        assert context.subject_id == str(user_id)
        assert context.role == Role.OPERATOR
        assert context.scopes == frozenset({"gateway:read", "gateway:write"})
        assert context.organization_id == organization_id
        assert context.client_id is None

    async def test_a_token_with_no_role_or_organization_claim_leaves_them_none(
        self, auth_service: AuthService, jwt_keypair
    ) -> None:
        private_key, _public_key = jwt_keypair
        token = encode_token({"sub": str(uuid.uuid4())}, private_key=private_key)

        context = await auth_service.authenticate_jwt(token)

        assert context.role is None
        assert context.organization_id is None
        assert context.scopes == frozenset()

    async def test_a_malformed_token_raises_authentication_error(
        self, auth_service: AuthService
    ) -> None:
        with pytest.raises(AuthenticationError):
            await auth_service.authenticate_jwt("not-a-real-token")

    async def test_a_token_signed_by_a_different_key_raises_authentication_error(
        self, auth_service: AuthService
    ) -> None:
        other_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other_pem = other_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("ascii")
        token = _token(other_pem)

        with pytest.raises(AuthenticationError):
            await auth_service.authenticate_jwt(token)

    async def test_an_expired_token_raises_authentication_error(
        self, auth_service: AuthService, jwt_keypair
    ) -> None:
        private_key, _public_key = jwt_keypair
        token = encode_token({"sub": str(uuid.uuid4())}, private_key=private_key, ttl_seconds=-3600)

        with pytest.raises(AuthenticationError):
            await auth_service.authenticate_jwt(token)


class TestAuthenticateApiKey:
    async def test_a_valid_key_produces_a_context_with_scopes_and_client(
        self, auth_service: AuthService, make_api_key, organization_id
    ) -> None:
        raw_key, stored = await make_api_key(scopes=["gateway:read"])

        context = await auth_service.authenticate_api_key(raw_key)

        assert context.method == AuthenticationMethod.API_KEY
        assert context.subject_id == str(stored.id)
        assert context.scopes == frozenset({"gateway:read"})
        assert context.client_id == stored.client_id
        assert context.organization_id == organization_id
        assert context.role is None

    async def test_an_invalid_key_raises_authentication_error(
        self, auth_service: AuthService
    ) -> None:
        with pytest.raises(AuthenticationError):
            await auth_service.authenticate_api_key("not-a-real-key")

    async def test_source_ip_outside_the_allowlist_raises_authentication_error(
        self, auth_service: AuthService, make_api_key
    ) -> None:
        raw_key, _stored = await make_api_key(scopes=[], ip_allowlist=["10.0.0.1"])

        with pytest.raises(AuthenticationError):
            await auth_service.authenticate_api_key(raw_key, source_ip="203.0.113.5")

    async def test_source_ip_inside_the_allowlist_succeeds(
        self, auth_service: AuthService, make_api_key
    ) -> None:
        raw_key, _stored = await make_api_key(scopes=[], ip_allowlist=["10.0.0.1"])

        context = await auth_service.authenticate_api_key(raw_key, source_ip="10.0.0.1")

        assert context.method == AuthenticationMethod.API_KEY


class TestAuthenticateAnonymous:
    def test_returns_an_anonymous_context_with_no_subject(self, auth_service: AuthService) -> None:
        context = auth_service.authenticate_anonymous()

        assert context == AuthContext(method=AuthenticationMethod.ANONYMOUS, subject_id=None)


class TestAuthorizeRequestOrganizationIsolation:
    def test_denies_when_the_callers_organization_does_not_match_the_target(
        self, auth_service: AuthService, organization_id
    ) -> None:
        other_org = uuid.uuid4()
        context = AuthContext(
            method=AuthenticationMethod.JWT,
            subject_id="user-1",
            role=Role.SUPER_ADMIN,
            organization_id=other_org,
        )

        decision = auth_service.authorize_request(
            context, target_organization_id=organization_id, required_permission=None
        )

        assert decision.granted is False
        assert "organization" in decision.reason.lower()

    def test_a_matching_organization_proceeds_past_the_isolation_check(
        self, auth_service: AuthService, organization_id
    ) -> None:
        context = AuthContext(
            method=AuthenticationMethod.JWT,
            subject_id="user-1",
            role=Role.VIEWER,
            organization_id=organization_id,
        )

        decision = auth_service.authorize_request(
            context, target_organization_id=organization_id, required_permission=Permission.READ
        )

        assert decision.granted is True

    def test_a_caller_with_no_organization_claim_is_never_isolation_checked(
        self, auth_service: AuthService, organization_id
    ) -> None:
        # Per `AuthContext.organization_id`'s own docstring: some callers
        # (e.g. a cross-org service account JWT) carry no organization
        # claim at all -- `authorize_request`'s isolation check only
        # fires when `context.organization_id is not None`, so this
        # caller skips straight to the next check regardless of which
        # organization the request targets.
        context = AuthContext(
            method=AuthenticationMethod.JWT,
            subject_id="svc-1",
            role=Role.SUPER_ADMIN,
            organization_id=None,
        )

        decision = auth_service.authorize_request(
            context, target_organization_id=organization_id, required_permission=Permission.READ
        )

        assert decision.granted is True


class TestAuthorizeRequestScopes:
    def test_denies_when_a_required_scope_is_missing(
        self, auth_service: AuthService, organization_id
    ) -> None:
        context = AuthContext(
            method=AuthenticationMethod.API_KEY,
            subject_id="key-1",
            scopes=frozenset({"gateway:read"}),
            organization_id=organization_id,
        )

        decision = auth_service.authorize_request(
            context,
            target_organization_id=organization_id,
            required_permission=None,
            required_scopes=["gateway:read", "gateway:write"],
        )

        assert decision.granted is False
        assert "gateway:write" in decision.reason

    def test_allows_when_every_required_scope_is_present(
        self, auth_service: AuthService, organization_id
    ) -> None:
        context = AuthContext(
            method=AuthenticationMethod.API_KEY,
            subject_id="key-1",
            scopes=frozenset({"gateway:read", "gateway:write"}),
            organization_id=organization_id,
        )

        decision = auth_service.authorize_request(
            context,
            target_organization_id=organization_id,
            required_permission=None,
            required_scopes=["gateway:read"],
        )

        assert decision.granted is True

    def test_no_required_scopes_skips_the_scope_check_entirely(
        self, auth_service: AuthService, organization_id
    ) -> None:
        context = AuthContext(
            method=AuthenticationMethod.API_KEY,
            subject_id="key-1",
            scopes=frozenset(),
            organization_id=organization_id,
        )

        decision = auth_service.authorize_request(
            context,
            target_organization_id=organization_id,
            required_permission=None,
            required_scopes=None,
        )

        assert decision.granted is True


class TestAuthorizeRequestRbac:
    def test_no_permission_required_grants_even_with_no_role(
        self, auth_service: AuthService, organization_id
    ) -> None:
        context = AuthContext(
            method=AuthenticationMethod.API_KEY, subject_id="key-1", organization_id=organization_id
        )

        decision = auth_service.authorize_request(
            context, target_organization_id=organization_id, required_permission=None
        )

        assert decision.granted is True
        assert context.role is None

    def test_denies_without_crashing_when_role_is_none_and_a_permission_is_required(
        self, auth_service: AuthService, organization_id
    ) -> None:
        # A caller authenticated by API key with no RBAC role attached
        # (e.g. scope-only access) hitting a route that requires a
        # permission must be denied cleanly, not raise.
        context = AuthContext(
            method=AuthenticationMethod.API_KEY, subject_id="key-1", organization_id=organization_id
        )

        decision = auth_service.authorize_request(
            context, target_organization_id=organization_id, required_permission=Permission.READ
        )

        assert decision.granted is False
        assert "role" in decision.reason.lower()

    def test_grants_when_the_role_holds_the_required_permission(
        self, auth_service: AuthService, organization_id
    ) -> None:
        context = AuthContext(
            method=AuthenticationMethod.JWT,
            subject_id="user-1",
            role=Role.VIEWER,
            organization_id=organization_id,
        )

        decision = auth_service.authorize_request(
            context, target_organization_id=organization_id, required_permission=Permission.READ
        )

        assert decision.granted is True

    def test_denies_when_the_role_lacks_the_required_permission(
        self, auth_service: AuthService, organization_id
    ) -> None:
        context = AuthContext(
            method=AuthenticationMethod.JWT,
            subject_id="user-1",
            role=Role.VIEWER,
            organization_id=organization_id,
        )

        decision = auth_service.authorize_request(
            context, target_organization_id=organization_id, required_permission=Permission.ADMIN
        )

        assert decision.granted is False
        assert "lacks" in decision.reason

    def test_super_admin_holds_every_permission(
        self, auth_service: AuthService, organization_id
    ) -> None:
        context = AuthContext(
            method=AuthenticationMethod.JWT,
            subject_id="user-1",
            role=Role.SUPER_ADMIN,
            organization_id=organization_id,
        )

        decision = auth_service.authorize_request(
            context, target_organization_id=organization_id, required_permission=Permission.ADMIN
        )

        assert decision.granted is True


class TestEndToEndJwtFlow:
    async def test_a_real_signed_token_flows_through_authentication_and_authorization(
        self, auth_service: AuthService, jwt_keypair, organization_id
    ) -> None:
        private_key, _public_key = jwt_keypair
        token = _token(private_key, role="organization_admin", organization_id=str(organization_id))

        context = await auth_service.authenticate_jwt(token)
        decision = auth_service.authorize_request(
            context, target_organization_id=organization_id, required_permission=Permission.DELETE
        )

        assert decision.granted is True

    async def test_a_real_signed_token_targeting_a_foreign_organization_is_denied(
        self, auth_service: AuthService, jwt_keypair, organization_id
    ) -> None:
        private_key, _public_key = jwt_keypair
        token = _token(private_key, role="super_admin", organization_id=str(uuid.uuid4()))

        context = await auth_service.authenticate_jwt(token)
        decision = auth_service.authorize_request(
            context, target_organization_id=organization_id, required_permission=Permission.READ
        )

        assert decision.granted is False
