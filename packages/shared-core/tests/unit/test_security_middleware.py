"""Tests for JWT/session validation ASGI middleware."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fakeredis import FakeAsyncRedis
from shared_core.cache.manager import CacheManager
from shared_core.enums import Role
from shared_core.security.context import get_security_context
from shared_core.security.jwt import encode_token
from shared_core.security.middleware import JwtAuthenticationMiddleware, SessionValidationMiddleware
from shared_core.security.sessions import SessionManager
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient


@pytest.fixture(scope="module")
def rsa_keypair() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )
    return private_pem, public_pem


async def _echo_context(request):  # type: ignore[no-untyped-def]
    context = get_security_context()
    return JSONResponse(
        {
            "user_id": str(context.user_id) if context.user_id else None,
            "role": context.role.value if context.role else None,
            "auth_method": context.auth_method,
        }
    )


def _build_app(public_key: str) -> Starlette:
    app = Starlette(routes=[Route("/", _echo_context)])
    app.add_middleware(JwtAuthenticationMiddleware, public_key=public_key)
    return app


def test_binds_security_context_from_valid_bearer_token(rsa_keypair: tuple[str, str]) -> None:
    private_key, public_key = rsa_keypair
    user_id = "550e8400-e29b-41d4-a716-446655440000"
    token = encode_token({"sub": user_id, "role": "operator"}, private_key=private_key)
    client = TestClient(_build_app(public_key))

    response = client.get("/", headers={"Authorization": f"Bearer {token}"})

    body = response.json()
    assert body["user_id"] == user_id
    assert body["role"] == Role.OPERATOR.value
    assert body["auth_method"] == "jwt"


def test_leaves_context_unbound_without_a_token(rsa_keypair: tuple[str, str]) -> None:
    _, public_key = rsa_keypair
    client = TestClient(_build_app(public_key))

    response = client.get("/")

    body = response.json()
    assert body["user_id"] is None


def test_leaves_context_unbound_for_an_invalid_token(rsa_keypair: tuple[str, str]) -> None:
    _, public_key = rsa_keypair
    client = TestClient(_build_app(public_key))

    response = client.get("/", headers={"Authorization": "Bearer not-a-real-token"})

    body = response.json()
    assert body["user_id"] is None


def test_resets_context_after_the_request(rsa_keypair: tuple[str, str]) -> None:
    private_key, public_key = rsa_keypair
    token = encode_token({"sub": "550e8400-e29b-41d4-a716-446655440000"}, private_key=private_key)
    client = TestClient(_build_app(public_key))

    client.get("/", headers={"Authorization": f"Bearer {token}"})

    assert get_security_context().user_id is None


async def test_jwt_middleware_passes_through_non_http_scopes() -> None:
    calls: list[str] = []

    async def inner_app(scope, receive, send):  # type: ignore[no-untyped-def]
        calls.append(scope["type"])

    middleware = JwtAuthenticationMiddleware(inner_app, public_key="unused")

    await middleware({"type": "lifespan"}, None, None)  # type: ignore[arg-type]

    assert calls == ["lifespan"]


# --- SessionValidationMiddleware ---


@pytest.fixture
async def redis_client() -> AsyncIterator[FakeAsyncRedis]:
    client = FakeAsyncRedis()
    yield client
    await client.aclose()


@pytest.fixture
def session_manager(redis_client: FakeAsyncRedis) -> SessionManager:
    return SessionManager(CacheManager(redis_client))


async def _echo_session_state(request):  # type: ignore[no-untyped-def]
    session = getattr(request.state, "session", None)
    return JSONResponse({"has_session": session is not None})


async def test_session_middleware_binds_state_for_valid_session_cookie(
    session_manager: SessionManager,
) -> None:
    session = await session_manager.create_session(user_id="user-1")

    app = Starlette(routes=[Route("/", _echo_session_state)])
    app.add_middleware(SessionValidationMiddleware, session_manager=session_manager)
    client = TestClient(app, cookies={"session_id": session.session_id})

    response = client.get("/")

    assert response.json()["has_session"] is True


def test_session_middleware_leaves_state_unset_without_cookie(
    session_manager: SessionManager,
) -> None:
    app = Starlette(routes=[Route("/", _echo_session_state)])
    app.add_middleware(SessionValidationMiddleware, session_manager=session_manager)
    client = TestClient(app)

    response = client.get("/")

    assert response.json()["has_session"] is False


def test_session_middleware_leaves_state_unset_for_invalid_session(
    session_manager: SessionManager,
) -> None:
    app = Starlette(routes=[Route("/", _echo_session_state)])
    app.add_middleware(SessionValidationMiddleware, session_manager=session_manager)
    client = TestClient(app, cookies={"session_id": "does-not-exist"})

    response = client.get("/")

    assert response.json()["has_session"] is False


async def test_session_middleware_passes_through_non_http_scopes(
    session_manager: SessionManager,
) -> None:
    calls: list[str] = []

    async def inner_app(scope, receive, send):  # type: ignore[no-untyped-def]
        calls.append(scope["type"])

    middleware = SessionValidationMiddleware(inner_app, session_manager=session_manager)

    await middleware({"type": "lifespan"}, None, None)  # type: ignore[arg-type]

    assert calls == ["lifespan"]
