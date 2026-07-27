"""Maps a :class:`~app.models.validation_check.ValidationCheck`'s own
``collector_key`` onto the actual collector function that gathers its
data ("Reusable Check Libraries").
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from shared_core.exceptions.validation import ValidationError

from app.collectors.context import CollectorContext
from app.collectors.network import (
    collect_certificate,
    collect_connectivity,
    collect_dns,
    collect_port,
)
from app.collectors.remote import collect_via_automation_job
from app.collectors.service_state import (
    collect_configuration_compliance,
    collect_configuration_drift,
    collect_discovery_job,
    collect_inventory_asset,
    collect_inventory_topology,
    collect_workflow_instance,
)
from app.models.validation_check import ValidationCheck
from app.models.validation_target import ValidationTarget

Collector = Callable[
    [ValidationCheck, ValidationTarget, CollectorContext], Awaitable[dict[str, Any]]
]

_DEFAULT_COLLECTORS: dict[str, Collector] = {
    "connectivity": collect_connectivity,
    "port": collect_port,
    "dns": collect_dns,
    "certificate": collect_certificate,
    "automation_job": collect_via_automation_job,
    "inventory_asset": collect_inventory_asset,
    "inventory_topology": collect_inventory_topology,
    "configuration_drift": collect_configuration_drift,
    "configuration_compliance": collect_configuration_compliance,
    "workflow_instance": collect_workflow_instance,
    "discovery_job": collect_discovery_job,
}


class CollectorRegistry:
    """Looks up and invokes the collector named by a check's own ``collector_key``."""

    def __init__(self, collectors: dict[str, Collector] | None = None) -> None:
        self._collectors = dict(collectors) if collectors is not None else dict(_DEFAULT_COLLECTORS)

    def register(self, collector_key: str, collector: Collector) -> None:
        """Register a custom collector under *collector_key* ("Custom Checks")."""
        self._collectors[collector_key] = collector

    async def collect(
        self, check: ValidationCheck, target: ValidationTarget, context: CollectorContext
    ) -> dict[str, Any]:
        """Run the collector named by *check*'s own ``collector_key``.

        Raises:
            ValidationError: If no collector is registered under that key.
        """
        collector = self._collectors.get(check.collector_key)
        if collector is None:
            raise ValidationError(
                f"Check {check.id!r} names unknown collector {check.collector_key!r}."
            )
        return await collector(check, target, context)


__all__ = ["Collector", "CollectorRegistry"]
