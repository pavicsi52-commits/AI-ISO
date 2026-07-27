"""Delegated collectors -- OS-level and application-level check types
(``DISK_USAGE``/``CPU``/``MEMORY``/``PROCESSES``/``OPERATING_SYSTEM``/
``KERNEL``/``PACKAGES``/``SERVICES``/``SECURITY_POLICIES``/
``COMPLIANCE_POLICIES``/``AUTHENTICATION``/``CUSTOM``) that genuinely
require remote code execution on the target this service has no direct
connectivity of its own to perform. Every one of these delegates to
``services/automation-service`` -- the same "this service dispatches,
automation-service actually connects" split
``services/workflow-runtime-service``'s own ``TASK``/``CONNECTOR``
node handler already established, rather than this service
reimplementing SSH/WinRM/Redfish/SNMP itself.

``check.parameters["job_id"]`` names the automation job that performs
the actual remote collection; its own completed execution's ``result``
field (assumed to be a flat JSON object of collected metrics, e.g.
``{"disk_usage_percent": 92.5}``) becomes this collector's own returned
data.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.collectors.context import CollectorContext
from app.models.validation_check import ValidationCheck
from app.models.validation_target import ValidationTarget


async def collect_via_automation_job(
    check: ValidationCheck, target: ValidationTarget, context: CollectorContext
) -> dict[str, Any]:
    """Dispatch *check*'s own configured automation job against *target*
    and return its own result as collected data.

    Raises:
        ValidationError: If *check* has no ``job_id`` in its own ``parameters``.
    """
    job_id_raw = check.parameters.get("job_id")
    if job_id_raw is None:
        raise ValidationError(
            f"Check {check.id!r} (collector 'automation_job') has no 'job_id' "
            "in its own parameters."
        )
    target_external_id = target.external_id
    execution = await context.automation.execute_and_wait(
        UUID(str(job_id_raw)),
        variables={"target_external_id": target_external_id},
        target_ids=[UUID(target_external_id)] if _looks_like_uuid(target_external_id) else None,
    )
    result = execution.get("result")
    return dict(result) if isinstance(result, dict) else {"execution_status": execution["status"]}


def _looks_like_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


__all__ = ["collect_via_automation_job"]
