"""Plugin Framework health.

Per docs/029_Enterprise_Plugin_Framework.md.txt "HEALTH": Plugin
Status, Errors, Execution Count, Dependency Status. Computed entirely
from this process's own
:class:`~shared_core.plugins.registry.PluginRegistry` state -- unlike
frameworks with one shared infrastructure dependency to probe (e.g.
:mod:`shared_core.workflow.health`'s RabbitMQ check), a plugin's
"health" is fundamentally about its own lifecycle state, not a live
external connection this framework itself owns. Reuses
:func:`shared_core.monitoring.status.calculate_status` (Prompt 023) for
the worst-case rollup, matching every other Prompt 018-028 framework's
own health.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared_core.enums.health_status import HealthStatus
from shared_core.monitoring.status import calculate_status
from shared_core.plugins.lifecycle import PluginState
from shared_core.plugins.registry import PluginRegistry

_UNHEALTHY_STATES = frozenset({PluginState.FAILED})


@dataclass(frozen=True, slots=True)
class PluginHealthReport:
    """A point-in-time snapshot of one plugin's health ("Plugin Status")."""

    plugin_id: str
    status: HealthStatus
    state: PluginState
    error: str | None = None


def build_plugin_health_report(
    plugin_id: str, state: PluginState, *, error: str | None = None
) -> PluginHealthReport:
    """Build a :class:`PluginHealthReport` for one plugin ("Errors")."""
    status = HealthStatus.UNHEALTHY if state in _UNHEALTHY_STATES else HealthStatus.HEALTHY
    return PluginHealthReport(plugin_id=plugin_id, status=status, state=state, error=error)


@dataclass(frozen=True, slots=True)
class PluginFrameworkHealthReport:
    """A point-in-time snapshot of the whole plugin framework's health."""

    status: HealthStatus
    installed_count: int
    running_count: int
    failed_count: int
    reports: tuple[PluginHealthReport, ...]


def build_framework_health_report(registry: PluginRegistry) -> PluginFrameworkHealthReport:
    """Build a full :class:`PluginFrameworkHealthReport` from *registry*'s current state.

    Covers "Execution Count" (``installed_count``) and "Dependency
    Status" indirectly -- a dependency-unsatisfiable plugin never
    leaves :class:`~shared_core.plugins.lifecycle.PluginState.FAILED`,
    which this rolls into the overall status.
    """
    reports = tuple(
        build_plugin_health_report(record.manifest.metadata.plugin_id, record.lifecycle.state)
        for record in registry.list_plugins()
    )
    overall_status = calculate_status([report.status for report in reports])
    return PluginFrameworkHealthReport(
        status=overall_status,
        installed_count=len(reports),
        running_count=len(registry.list_enabled()),
        failed_count=sum(1 for report in reports if report.status == HealthStatus.UNHEALTHY),
        reports=reports,
    )


__all__ = [
    "PluginFrameworkHealthReport",
    "PluginHealthReport",
    "build_framework_health_report",
    "build_plugin_health_report",
]
