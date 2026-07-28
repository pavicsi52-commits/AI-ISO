"""Collectors that read another service's own already-recorded state
rather than performing a live probe -- backing docs/044's own
"INTEGRATIONS" section (Inventory, Discovery, Configuration Management,
Workflow Runtime, Validation). Every one of these is read-only and
non-invasive: it never triggers new work on the other service, only
reads what that service already knows, folding the result into this
target's own ``DEPENDENCY_HEALTH``/``COMPONENT_HEALTH`` signal. Matches
``services/validation-service``'s own
:mod:`app.collectors.service_state`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.collectors.context import CollectorContext
from app.models.monitoring_collector import MonitoringCollector
from app.models.monitoring_target import MonitoringTarget


async def collect_inventory_asset(
    _collector: MonitoringCollector, target: MonitoringTarget, context: CollectorContext
) -> dict[str, Any]:
    """The target's own live inventory-service asset record."""
    asset = await context.inventory.get_asset(UUID(target.external_id))
    return {"asset": asset, "status": asset.get("status")}


async def collect_configuration_drift(
    _collector: MonitoringCollector, target: MonitoringTarget, context: CollectorContext
) -> dict[str, Any]:
    """Already-recorded configuration drift for the target's own profile."""
    drift_records = await context.configuration.get_drift(
        target.organization_id, UUID(target.external_id)
    )
    unresolved = [record for record in drift_records if record.get("resolved_at") is None]
    return {"drift_records": drift_records, "unresolved_drift_count": len(unresolved)}


async def collect_configuration_compliance(
    _collector: MonitoringCollector, target: MonitoringTarget, context: CollectorContext
) -> dict[str, Any]:
    """Already-recorded compliance evaluations for the target's own profile."""
    records = await context.configuration.get_compliance(UUID(target.external_id))
    non_compliant = [record for record in records if record.get("status") != "compliant"]
    return {"compliance_records": records, "non_compliant_count": len(non_compliant)}


async def collect_workflow_instance(
    _collector: MonitoringCollector, target: MonitoringTarget, context: CollectorContext
) -> dict[str, Any]:
    """The target's own live workflow-runtime-service instance status."""
    instance = await context.workflow.get_instance(UUID(target.external_id))
    steps = await context.workflow.list_steps(UUID(target.external_id))
    failed_steps = [step for step in steps if step.get("status") == "failed"]
    return {
        "instance_status": instance.get("status"),
        "step_count": len(steps),
        "failed_step_count": len(failed_steps),
    }


async def collect_discovery_job(
    _collector: MonitoringCollector, target: MonitoringTarget, context: CollectorContext
) -> dict[str, Any]:
    """The target's own discovery job summary."""
    job = await context.discovery.get_job(UUID(target.external_id))
    return {
        "discovered_asset_count": job.get("discovered_asset_count", 0),
        "discovered_relationship_count": job.get("discovered_relationship_count", 0),
        "job_status": job.get("status"),
    }


async def collect_validation_posture(
    _collector: MonitoringCollector, target: MonitoringTarget, context: CollectorContext
) -> dict[str, Any]:
    """The target's own most recent validation results."""
    results = await context.validation.get_results_for_target(target.id)
    failed = [result for result in results if result.get("status") == "failed"]
    return {"result_count": len(results), "failed_count": len(failed)}


__all__ = [
    "collect_configuration_compliance",
    "collect_configuration_drift",
    "collect_discovery_job",
    "collect_inventory_asset",
    "collect_validation_posture",
    "collect_workflow_instance",
]
