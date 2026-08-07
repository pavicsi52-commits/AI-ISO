"""Tests for ``app.services.health.PluginHealthService``.

Hits real network calls to already-running local containers --
``shared_core.monitoring.checks.check_http_reachable`` builds its own
internal ``httpx.AsyncClient`` and cannot be pointed at a test double
(see ``tests/conftest.py``'s own module docstring), so these tests point
at RabbitMQ's own management UI (``REACHABLE_HTTP_URL``, always up in
this environment) and a real loopback port nothing listens on
(``UNREACHABLE_HTTP_URL``).
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.enums.health_status import HealthStatus

from app.manifests.engine import compute_manifest_checksum
from app.models.installation import PluginInstallation
from app.services.health import PluginHealthService
from app.services.installation import PluginInstallationService
from app.services.plugin import PluginService
from tests.conftest import (
    REACHABLE_HTTP_URL,
    UNREACHABLE_HTTP_URL,
    MakePluginFn,
)


def _manifest(version: str = "1.0.0") -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "name": "Health Test Plugin",
        "publisher": "test-publisher",
        "category": "monitoring",
        "type": "custom_plugin",
        "version": version,
        "entry_points": ["main:run"],
        "supported_platform_versions": [
            {"platform": "aiios", "version_constraint": ">=1.0.0,<2.0.0"}
        ],
        "permissions_required": [],
        "dependencies": [],
        "api_requirements": [],
        "health_checks": [],
    }
    manifest["checksum"] = compute_manifest_checksum(manifest)
    return manifest


async def _make_installation(
    make_plugin: MakePluginFn,
    plugin_service: PluginService,
    installation_service: PluginInstallationService,
    organization_id: uuid.UUID,
    *,
    slug: str = "health-plugin",
    health_check_url: str | None = None,
) -> PluginInstallation:
    plugin = await make_plugin(slug=slug)
    await plugin_service.submit_manifest(
        organization_id, plugin.id, version_number="1.0.0", manifest=_manifest()
    )
    await plugin_service.publish(organization_id, plugin.id, version_number="1.0.0")
    installation = await installation_service.install(organization_id, plugin.id)
    if health_check_url is not None:
        installation = await installation_service.configure(
            organization_id,
            installation.id,
            configuration={"health_check_url": health_check_url},
        )
    return installation


async def test_probe_reachable_url_is_healthy_with_latency(
    health_service: PluginHealthService,
    make_plugin: MakePluginFn,
    plugin_service: PluginService,
    installation_service: PluginInstallationService,
    organization_id: uuid.UUID,
) -> None:
    installation = await _make_installation(
        make_plugin,
        plugin_service,
        installation_service,
        organization_id,
        slug="health-reachable",
        health_check_url=REACHABLE_HTTP_URL,
    )

    result = await health_service.probe(installation)

    assert result.status == HealthStatus.HEALTHY
    assert result.error is None
    assert result.latency_ms is not None
    assert result.latency_ms >= 0
    assert result.consecutive_failures == 0
    assert result.recovery_attempted is False
    assert result.plugin_installation_id == installation.id
    assert result.organization_id == organization_id


async def test_probe_unreachable_url_is_not_healthy_with_error(
    health_service: PluginHealthService,
    make_plugin: MakePluginFn,
    plugin_service: PluginService,
    installation_service: PluginInstallationService,
    organization_id: uuid.UUID,
) -> None:
    installation = await _make_installation(
        make_plugin,
        plugin_service,
        installation_service,
        organization_id,
        slug="health-unreachable",
        health_check_url=UNREACHABLE_HTTP_URL,
    )

    result = await health_service.probe(installation)

    assert result.status != HealthStatus.HEALTHY
    assert result.error is not None
    assert result.consecutive_failures == 1


async def test_probe_with_no_health_check_url_is_unknown(
    health_service: PluginHealthService,
    make_plugin: MakePluginFn,
    plugin_service: PluginService,
    installation_service: PluginInstallationService,
    organization_id: uuid.UUID,
) -> None:
    installation = await _make_installation(
        make_plugin,
        plugin_service,
        installation_service,
        organization_id,
        slug="health-unconfigured",
    )

    result = await health_service.probe(installation)

    assert result.status == HealthStatus.UNKNOWN
    assert result.error is not None
    assert "health_check_url" in result.error
    assert result.latency_ms is None
    # UNKNOWN isn't HEALTHY, so it still counts toward the failure streak --
    # only a genuinely HEALTHY probe resets it.
    assert result.consecutive_failures == 1
    assert result.recovery_attempted is False


async def test_consecutive_failures_carries_forward_and_resets(
    health_service: PluginHealthService,
    make_plugin: MakePluginFn,
    plugin_service: PluginService,
    installation_service: PluginInstallationService,
    organization_id: uuid.UUID,
) -> None:
    installation = await _make_installation(
        make_plugin,
        plugin_service,
        installation_service,
        organization_id,
        slug="health-streak",
        health_check_url=UNREACHABLE_HTTP_URL,
    )

    first = await health_service.probe(installation)
    assert first.consecutive_failures == 1

    second = await health_service.probe(installation)
    assert second.consecutive_failures == 2

    # Reconfigure to a reachable endpoint and probe again -- the streak resets.
    reconfigured = await installation_service.configure(
        organization_id, installation.id, configuration={"health_check_url": REACHABLE_HTTP_URL}
    )
    third = await health_service.probe(reconfigured)
    assert third.status == HealthStatus.HEALTHY
    assert third.consecutive_failures == 0


async def test_recovery_attempted_once_failure_threshold_reached(
    health_service: PluginHealthService,
    make_plugin: MakePluginFn,
    plugin_service: PluginService,
    installation_service: PluginInstallationService,
    organization_id: uuid.UUID,
) -> None:
    installation = await _make_installation(
        make_plugin,
        plugin_service,
        installation_service,
        organization_id,
        slug="health-recovery",
        health_check_url=UNREACHABLE_HTTP_URL,
    )
    threshold = health_service._failure_threshold

    last_result = None
    for _ in range(threshold):
        last_result = await health_service.probe(installation)

    assert last_result is not None
    assert last_result.consecutive_failures == threshold
    assert last_result.recovery_attempted is True

    # Before the threshold was reached, recovery must not have been attempted.
    history = await health_service.list_for_installation(installation.id)
    # history is newest-first; every entry with consecutive_failures < threshold
    # must have recovery_attempted False.
    for entry in history:
        if entry.consecutive_failures < threshold:
            assert entry.recovery_attempted is False


async def test_list_for_installation_returns_newest_first(
    health_service: PluginHealthService,
    make_plugin: MakePluginFn,
    plugin_service: PluginService,
    installation_service: PluginInstallationService,
    organization_id: uuid.UUID,
) -> None:
    installation = await _make_installation(
        make_plugin,
        plugin_service,
        installation_service,
        organization_id,
        slug="health-list",
        health_check_url=REACHABLE_HTTP_URL,
    )

    first = await health_service.probe(installation)
    second = await health_service.probe(installation)

    history = await health_service.list_for_installation(installation.id)
    assert len(history) == 2
    assert history[0].id == second.id
    assert history[1].id == first.id


async def test_latest_for_installation(
    health_service: PluginHealthService,
    make_plugin: MakePluginFn,
    plugin_service: PluginService,
    installation_service: PluginInstallationService,
    organization_id: uuid.UUID,
) -> None:
    installation = await _make_installation(
        make_plugin,
        plugin_service,
        installation_service,
        organization_id,
        slug="health-latest",
        health_check_url=REACHABLE_HTTP_URL,
    )

    assert await health_service.latest_for_installation(installation.id) is None

    await health_service.probe(installation)
    second = await health_service.probe(installation)

    latest = await health_service.latest_for_installation(installation.id)
    assert latest is not None
    assert latest.id == second.id
