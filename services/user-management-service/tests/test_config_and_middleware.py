"""Small, focused unit tests for pieces that don't need real infrastructure:
JWT public-key loading, the production-vs-development CORS policy
choice, and the ASGI timing middleware's non-HTTP passthrough.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from shared_core.config.environment import Environment
from shared_core.config.settings import ApplicationSettings
from shared_core.exceptions.dependency import DependencyError
from starlette.types import Message, Receive, Scope, Send

from app.config.keys import load_public_key
from app.config.settings import get_settings
from app.core.factory import _build_cors_config
from app.middleware.timing import TimingMiddleware


def test_load_public_key_reads_existing_file(tmp_path: Path) -> None:
    key_path = tmp_path / "public.pem"
    key_path.write_text(
        "-----BEGIN PUBLIC KEY-----\nabc\n-----END PUBLIC KEY-----\n", encoding="ascii"
    )

    loaded = load_public_key(str(key_path))

    assert "BEGIN PUBLIC KEY" in loaded


def test_load_public_key_raises_when_missing(tmp_path: Path) -> None:
    missing_path = tmp_path / "does-not-exist.pem"

    with pytest.raises(DependencyError):
        load_public_key(str(missing_path))


def test_build_cors_config_development_is_permissive() -> None:
    settings = get_settings()

    cors = _build_cors_config(settings)

    assert cors.allow_origins == ("*",)
    assert cors.allow_credentials is False


def test_build_cors_config_production_uses_explicit_origins() -> None:
    settings = get_settings()
    production_settings = replace(
        settings, application=ApplicationSettings(environment=Environment.PRODUCTION)
    )

    cors = _build_cors_config(production_settings)

    assert cors.allow_credentials is True
    assert "*" not in cors.allow_origins


async def test_timing_middleware_passes_through_non_http_scopes() -> None:
    events: list[str] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        del receive, send
        events.append(scope["type"])

    middleware = TimingMiddleware(app)

    async def _receive() -> Message:
        raise AssertionError("should not be called for a lifespan scope")

    async def _send(_message: Message) -> None:
        raise AssertionError("should not be called for a lifespan scope")

    await middleware({"type": "lifespan"}, _receive, _send)

    assert events == ["lifespan"]
