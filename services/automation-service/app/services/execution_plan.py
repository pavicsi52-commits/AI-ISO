"""Reusable, ordered execution plans. Per docs/040 "EXECUTION PLANS"
"Support": Pre-check Tasks, Preparation, Validation, Execution,
Post-validation, Cleanup, Notifications, Rollback Planning, Approval
Gates -- each phase is a caller-defined entry in ``steps``/
``approval_gates``, this service only owns the plan row's own CRUD.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.automation_execution_plan import AutomationExecutionPlan
from app.repositories.automation_execution_plan import AutomationExecutionPlanRepository


class AutomationExecutionPlanService:
    """Creates, reads, updates, and deletes reusable execution plans."""

    def __init__(self, plans: AutomationExecutionPlanRepository) -> None:
        self._plans = plans

    async def get_by_id(self, plan_id: UUID) -> AutomationExecutionPlan:
        """Return the execution plan identified by *plan_id*.

        Raises:
            NotFoundError: If no such plan exists.
        """
        return await self._plans.require_by_id(plan_id)

    async def list_for_org(self, organization_id: UUID) -> list[AutomationExecutionPlan]:
        """Every execution plan belonging to *organization_id*."""
        return await self._plans.list_for_org(organization_id)

    async def list_for_job(self, job_id: UUID) -> list[AutomationExecutionPlan]:
        """Every execution plan attached to *job_id*."""
        return await self._plans.list_for_job(job_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        job_id: UUID | None,
        name: str,
        steps: list[dict[str, Any]],
        approval_gates: list[dict[str, Any]],
        rollback_plan: dict[str, Any] | None,
    ) -> AutomationExecutionPlan:
        """Define a new reusable, ordered execution plan."""
        return await self._plans.create(
            AutomationExecutionPlan(
                organization_id=organization_id,
                job_id=job_id,
                name=name,
                steps=steps,
                approval_gates=approval_gates,
                rollback_plan=rollback_plan,
            )
        )

    async def update(
        self,
        plan_id: UUID,
        *,
        name: str,
        steps: list[dict[str, Any]],
        approval_gates: list[dict[str, Any]],
        rollback_plan: dict[str, Any] | None,
    ) -> AutomationExecutionPlan:
        """Replace an execution plan's phases/gates."""
        plan = await self.get_by_id(plan_id)
        plan.name = name
        plan.steps = steps
        plan.approval_gates = approval_gates
        plan.rollback_plan = rollback_plan
        return await self._plans.update(plan)

    async def delete(self, plan_id: UUID) -> None:
        """Soft-delete an execution plan."""
        await self._plans.delete(plan_id)


__all__ = ["AutomationExecutionPlanService"]
