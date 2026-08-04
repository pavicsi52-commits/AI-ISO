"""An organization's own priority-escalation policy, one band at a time."""

from __future__ import annotations

from uuid import UUID

from app.models.enums import JobPriority
from app.models.priority import JobPriorityPolicy
from app.repositories.priority import JobPriorityPolicyRepository


class PriorityService:
    """Reads and writes an organization's escalation policy per priority band."""

    def __init__(self, policies: JobPriorityPolicyRepository) -> None:
        self._policies = policies

    async def set_policy(
        self,
        organization_id: UUID,
        priority: JobPriority,
        *,
        label: str,
        color: str | None = None,
        escalate_after_minutes: int | None = None,
        escalate_to: JobPriority | None = None,
    ) -> JobPriorityPolicy:
        """Create or replace this organization's policy for one band."""
        existing = await self._policies.get_for_priority(organization_id, priority)
        row = existing or JobPriorityPolicy(organization_id=organization_id, priority=priority)
        row.label = label
        row.color = color
        row.escalate_after_minutes = escalate_after_minutes
        row.escalate_to = escalate_to
        return await (self._policies.update(row) if existing else self._policies.create(row))

    async def get_policy(
        self, organization_id: UUID, priority: JobPriority
    ) -> JobPriorityPolicy | None:
        """This organization's policy for one band, if configured."""
        return await self._policies.get_for_priority(organization_id, priority)

    async def list_policies(self, organization_id: UUID) -> list[JobPriorityPolicy]:
        """Every band this organization has configured."""
        return await self._policies.list_for_org(organization_id)


__all__ = ["PriorityService"]
