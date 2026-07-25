"""Tests for :mod:`app.connectors.registry`."""

from __future__ import annotations

from app.connectors.registry import build_connector_registry
from app.connectors.ssh_connector import SshConnector


class TestBuildConnectorRegistry:
    def test_registers_ssh_provider(self) -> None:
        registry = build_connector_registry()
        provider_cls = registry.get("ssh")
        assert provider_cls is SshConnector

    def test_returns_a_fresh_registry_each_call(self) -> None:
        first = build_connector_registry()
        second = build_connector_registry()
        assert first is not second
