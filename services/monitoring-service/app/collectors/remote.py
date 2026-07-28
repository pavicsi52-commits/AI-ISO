"""Delegated collection -- OS-level resource metrics (CPU/Memory/Disk/
Filesystem/IOPS/Process/Service Status) and the ``SSH``/``DATABASE``/
``CUSTOM_SCRIPT`` synthetic check types that genuinely require remote
code execution on the target this service has no direct connectivity
of its own to perform. Every one of these delegates to
``services/automation-service`` -- the same "this service dispatches,
automation-service actually connects" split
``services/validation-service``'s own :mod:`app.collectors.remote`
already established, rather than this service reimplementing SSH/
WinRM/Redfish/SNMP itself.

``parameters["job_id"]`` names the automation job that performs the
actual remote collection; its own completed execution's ``result``
field (assumed to be a flat JSON object of collected metrics, e.g.
``{"cpu_usage_percent": 42.5}``) becomes the returned data. The
low-level :func:`run_automation_job` is model-agnostic (takes a raw
``job_id``/``target_external_id`` rather than a specific owning row) so
both :func:`collect_via_automation_job` (for
:class:`~app.models.monitoring_collector.MonitoringCollector`-driven
recurring collection) and :mod:`app.collectors.synthetic`'s own
``SSH``/``DATABASE``/``CUSTOM_SCRIPT`` handlers (for
:class:`~app.models.monitoring_synthetic_test.MonitoringSyntheticTest`-
driven one-off probes) share the identical dispatch-and-wait logic.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.collectors.context import CollectorContext
from app.models.monitoring_collector import MonitoringCollector
from app.models.monitoring_target import MonitoringTarget


def _looks_like_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


async def run_automation_job(
    context: CollectorContext, job_id: UUID, target_external_id: str
) -> dict[str, Any]:
    """Dispatch *job_id* against *target_external_id* and return its own result."""
    execution = await context.automation.execute_and_wait(
        job_id,
        variables={"target_external_id": target_external_id},
        target_ids=[UUID(target_external_id)] if _looks_like_uuid(target_external_id) else None,
    )
    result = execution.get("result")
    return dict(result) if isinstance(result, dict) else {"execution_status": execution["status"]}


async def collect_via_automation_job(
    collector: MonitoringCollector, target: MonitoringTarget, context: CollectorContext
) -> dict[str, Any]:
    """Dispatch *collector*'s own configured automation job against
    *target* and return its own result as collected data.

    Raises:
        ValidationError: If *collector* has no ``job_id`` in its own ``parameters``.
    """
    job_id_raw = collector.parameters.get("job_id")
    if job_id_raw is None:
        raise ValidationError(
            f"Collector {collector.id!r} (collector_key {collector.collector_key!r}) has no "
            "'job_id' in its own parameters."
        )
    return await run_automation_job(context, UUID(str(job_id_raw)), target.external_id)


__all__ = ["collect_via_automation_job", "run_automation_job"]
