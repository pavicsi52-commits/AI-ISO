"""Collectors that read another service's own already-recorded state
rather than performing a live probe -- backing docs/043's own
"INVENTORY INTEGRATION"/"CONFIGURATION MANAGEMENT"/"WORKFLOW RUNTIME"/
"DISCOVERY INTEGRATION" sections. Every one of these is read-only and
non-invasive: it never triggers new work on the other service, only
reads what that service already knows.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.collectors.context import CollectorContext
from app.models.validation_check import ValidationCheck
from app.models.validation_target import ValidationTarget


async def collect_inventory_asset(
    _check: ValidationCheck, target: ValidationTarget, context: CollectorContext
) -> dict[str, Any]:
    """The target's own live inventory-service asset record ("Assets")."""
    asset = await context.inventory.get_asset(UUID(target.external_id))
    return {"asset": asset, "status": asset.get("status")}


async def collect_inventory_topology(
    check: ValidationCheck, target: ValidationTarget, context: CollectorContext
) -> dict[str, Any]:
    """The target's own topology graph ("Topology Consistency")."""
    query_kind = str(check.parameters.get("query_kind", "neighbors"))
    depth = int(check.parameters.get("depth", 1))
    topology = await context.inventory.get_topology(
        UUID(target.external_id), query_kind=query_kind, depth=depth
    )
    nodes = topology.get("nodes", [])
    return {"topology": topology, "node_count": len(nodes)}


async def collect_configuration_drift(
    _check: ValidationCheck, target: ValidationTarget, context: CollectorContext
) -> dict[str, Any]:
    """Already-recorded configuration drift for the target's own profile
    ("Configuration Drift").
    """
    drift_records = await context.configuration.get_drift(
        target.organization_id, UUID(target.external_id)
    )
    unresolved = [record for record in drift_records if record.get("resolved_at") is None]
    return {"drift_records": drift_records, "unresolved_drift_count": len(unresolved)}


async def collect_configuration_compliance(
    _check: ValidationCheck, target: ValidationTarget, context: CollectorContext
) -> dict[str, Any]:
    """Already-recorded compliance evaluations for the target's own
    profile ("Policy Compliance").
    """
    records = await context.configuration.get_compliance(UUID(target.external_id))
    non_compliant = [record for record in records if record.get("status") != "compliant"]
    return {"compliance_records": records, "non_compliant_count": len(non_compliant)}


async def collect_workflow_instance(
    _check: ValidationCheck, target: ValidationTarget, context: CollectorContext
) -> dict[str, Any]:
    """The target's own live workflow-runtime-service instance status
    ("Validation Nodes"/"Workflow Gates").
    """
    instance = await context.workflow.get_instance(UUID(target.external_id))
    steps = await context.workflow.list_steps(UUID(target.external_id))
    failed_steps = [step for step in steps if step.get("status") == "failed"]
    return {
        "instance_status": instance.get("status"),
        "step_count": len(steps),
        "failed_step_count": len(failed_steps),
    }


async def collect_discovery_job(
    _check: ValidationCheck, target: ValidationTarget, context: CollectorContext
) -> dict[str, Any]:
    """The target's own discovery job summary ("Discovery Accuracy")."""
    job = await context.discovery.get_job(UUID(target.external_id))
    return {
        "discovered_asset_count": job.get("discovered_asset_count", 0),
        "discovered_relationship_count": job.get("discovered_relationship_count", 0),
        "job_status": job.get("status"),
    }


__all__ = [
    "collect_configuration_compliance",
    "collect_configuration_drift",
    "collect_discovery_job",
    "collect_inventory_asset",
    "collect_inventory_topology",
    "collect_workflow_instance",
]
