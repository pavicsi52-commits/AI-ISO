"""Tests for environment-driven settings loading."""

from __future__ import annotations

import os

import pytest

from app.config.settings import Settings, get_settings


def test_defaults_apply_when_no_env_vars_set(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("AIIOS_"):
            monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)

    assert settings.environment == "development"
    assert settings.app_name == "gateway"
    assert settings.gateway_port == 8000


def test_env_vars_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIIOS_ENVIRONMENT", "production")
    monkeypatch.setenv("AIIOS_GATEWAY_PORT", "9000")

    settings = Settings(_env_file=None)

    assert settings.environment == "production"
    assert settings.gateway_port == 9000


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()

    first = get_settings()
    second = get_settings()

    assert first is second
    get_settings.cache_clear()
