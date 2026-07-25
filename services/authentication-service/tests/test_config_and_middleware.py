"""Small, focused unit tests for pieces that don't need real infrastructure:
JWT key loading/generation, the production-vs-development CORS policy
choice, and the ASGI timing middleware's non-HTTP passthrough.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from shared_core.config.environment import Environment
from shared_core.config.settings import ApplicationSettings
from starlette.types import Message, Receive, Scope, Send

import app.validators
import app.workers
from app.config.keys import generate_keypair, load_or_generate_keypair
from app.config.settings import get_settings
from app.core.factory import _build_cors_config
from app.middleware.timing import TimingMiddleware


def test_generate_keypair_returns_valid_pem_pair() -> None:
    private_pem, public_pem = generate_keypair()

    assert private_pem.startswith("-----BEGIN PRIVATE KEY-----")
    assert public_pem.startswith("-----BEGIN PUBLIC KEY-----")


def test_load_or_generate_keypair_generates_and_persists_when_missing(
    tmp_path: Path,
) -> None:
    private_path = tmp_path / "keys" / "private.pem"
    public_path = tmp_path / "keys" / "public.pem"

    private_pem, public_pem = load_or_generate_keypair(str(private_path), str(public_path))

    assert private_path.is_file()
    assert public_path.is_file()
    assert private_path.read_text(encoding="ascii") == private_pem
    assert public_path.read_text(encoding="ascii") == public_pem


def test_load_or_generate_keypair_loads_existing_files(tmp_path: Path) -> None:
    private_path = tmp_path / "private.pem"
    public_path = tmp_path / "public.pem"
    generated_private, generated_public = generate_keypair()
    private_path.write_text(generated_private, encoding="ascii")
    public_path.write_text(generated_public, encoding="ascii")

    loaded_private, loaded_public = load_or_generate_keypair(str(private_path), str(public_path))

    assert loaded_private == generated_private
    assert loaded_public == generated_public


def test_build_cors_config_development_is_permissive() -> None:
    settings = get_settings()

    cors = _build_cors_config(settings)

    assert cors.allow_origins == ("*",)
    assert cors.allow_credentials is False


def test_build_cors_config_production_uses_explicit_origins() -> None:
    settings = get_settings()
    production_settings = replace(
        settings,
        application=ApplicationSettings(environment=Environment.PRODUCTION),
    )

    cors = _build_cors_config(production_settings)

    assert cors.allow_origins == tuple(production_settings.service.cors_allowed_origins)
    assert cors.allow_credentials is True
    assert "*" not in cors.allow_origins


async def test_timing_middleware_passes_through_non_http_scopes() -> None:
    events: list[str] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        del receive, send
        events.append(scope["type"])

    middleware = TimingMiddleware(app)  # type: ignore[arg-type]

    async def _receive() -> Message:
        raise AssertionError("should not be called for a lifespan scope")

    async def _send(_message: Message) -> None:
        raise AssertionError("should not be called for a lifespan scope")

    await middleware({"type": "lifespan"}, _receive, _send)

    assert events == ["lifespan"]


def test_validators_and_workers_packages_import_cleanly() -> None:
    assert app.validators.__doc__
    assert app.workers.__doc__
