"""Tests for the application factory's security-related wiring."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config.settings import Settings, get_settings
from app.core.factory import _build_cors_config, create_app


def test_build_cors_config_development_is_permissive() -> None:
    settings = Settings(environment="development", _env_file=None)

    config = _build_cors_config(settings)

    assert config.allow_origins == ("*",)
    assert config.allow_credentials is False


def test_build_cors_config_production_uses_explicit_allowlist() -> None:
    settings = Settings(
        environment="production",
        cors_allowed_origins=["https://app.aiios.example"],
        _env_file=None,
    )

    config = _build_cors_config(settings)

    assert config.allow_origins == ("https://app.aiios.example",)
    assert config.allow_credentials is True


def test_response_carries_security_headers() -> None:
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "strict-transport-security" in response.headers
    get_settings.cache_clear()
