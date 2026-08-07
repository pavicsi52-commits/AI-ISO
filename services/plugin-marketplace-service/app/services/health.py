"""Installed plugin health monitoring (docs/059 "HEALTH MONITORING").

Reuses the same ``shared_core.monitoring.checks`` primitives every
other AI-IOS connectivity probe already does. Unlike a remote connector,
most plugin types have no network endpoint of their own to reach at
all -- a probe only has something real to check when the installation's
own ``configuration`` declares a ``health_check_url`` (the runtime
counterpart of the manifest's own declared ``health_checks``); otherwise
the honest answer is ``UNKNOWN``, not a fabricated ``HEALTHY``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.enums.health_status import HealthStatus
from shared_core.monitoring.checks import check_http_reachable

from app.models.health import PluginHealth
from app.models.installation import PluginInstallation
from app.repositories.health import PluginHealthRepository


class PluginHealthService:
    """Runs and records one automated health probe for an installed plugin instance."""

    def __init__(
        self,
        health: PluginHealthRepository,
        *,
        timeout_seconds: float = 5.0,
        failure_threshold: int = 3,
    ) -> None:
        self._health = health
        self._timeout_seconds = timeout_seconds
        self._failure_threshold = failure_threshold

    async def probe(self, installation: PluginInstallation) -> PluginHealth:
        """Probe *installation*'s own configured health-check endpoint, if any.

        ``consecutive_failures`` is carried forward from *installation*'s
        own most recent probe row -- ``PluginInstallation`` itself has no
        such column, since it would just be a cache of what
        ``plugin_health`` already records; the latest row is the single
        source of truth for the running streak.
        """
        previous = await self._health.get_latest(installation.id)
        previous_streak = previous.consecutive_failures if previous is not None else 0

        status, latency_ms, error = await self._probe_endpoint(installation)
        recovery_attempted = (
            status != HealthStatus.HEALTHY and previous_streak + 1 >= self._failure_threshold
        )
        return await self._health.create(
            PluginHealth(
                organization_id=installation.organization_id,
                plugin_installation_id=installation.id,
                status=status,
                latency_ms=latency_ms,
                checked_at=datetime.now(UTC),
                error=error,
                consecutive_failures=(0 if status == HealthStatus.HEALTHY else previous_streak + 1),
                recovery_attempted=recovery_attempted,
            )
        )

    async def _probe_endpoint(
        self, installation: PluginInstallation
    ) -> tuple[HealthStatus, float | None, str | None]:
        health_check_url = installation.configuration.get("health_check_url")
        if isinstance(health_check_url, str) and health_check_url:
            result = await check_http_reachable(
                str(installation.plugin_id),
                health_check_url,
                timeout_seconds=self._timeout_seconds,
            )
            return result.status, result.latency_ms, result.error
        return HealthStatus.UNKNOWN, None, "No 'health_check_url' configured for this installation."

    async def list_for_installation(
        self, plugin_installation_id: UUID, *, limit: int = 50
    ) -> list[PluginHealth]:
        """Recent health checks for one installation, newest first."""
        return await self._health.list_for_installation(plugin_installation_id, limit=limit)

    async def latest_for_installation(self, plugin_installation_id: UUID) -> PluginHealth | None:
        """The most recent health check for one installation, if any."""
        return await self._health.get_latest(plugin_installation_id)


__all__ = ["PluginHealthService"]
