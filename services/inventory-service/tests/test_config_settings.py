"""Tests for ``app/config/settings.py``."""

from __future__ import annotations

from app.config.settings import InventoryServiceSettings, build_settings, get_settings


def test_build_settings_uses_shared_aggregate_and_service_defaults() -> None:
    settings = build_settings()
    assert settings.service.port == 8007
    assert settings.database is not None
    assert settings.neo4j is not None
    assert settings.minio is not None


def test_build_settings_accepts_explicit_service_settings() -> None:
    service = InventoryServiceSettings(port=9999)
    settings = build_settings(service=service)
    assert settings.service.port == 9999


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


__all__: list[str] = []
