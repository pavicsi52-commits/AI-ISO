"""Resource-limit management. Per docs/033 "RESOURCE LIMITS".

No dedicated REST surface is named in docs/033's own endpoint list
(only Quotas has one) -- this service exists for programmatic
completeness, the same scope decision ``app/services/business_unit.py``
documents.
"""

from __future__ import annotations

from uuid import UUID

from app.models.organization_limits import OrganizationLimits
from app.repositories.organization_limits import OrganizationLimitsRepository


class OrganizationLimitsService:
    """Reads and updates an organization's resource limits."""

    def __init__(self, limits: OrganizationLimitsRepository) -> None:
        self._limits = limits

    async def get_or_create(self, organization_id: UUID) -> OrganizationLimits:
        """Return *organization_id*'s resource limits, creating defaults if missing."""
        existing = await self._limits.get_for_org(organization_id)
        if existing is not None:
            return existing
        return await self._limits.create(OrganizationLimits(organization_id=organization_id))

    async def update(
        self,
        organization_id: UUID,
        *,
        cpu_cores: int,
        memory_mb: int,
        storage_gb: int,
        queue_usage: int,
        concurrent_workflows: int,
        concurrent_jobs: int,
        concurrent_ai_tasks: int,
        concurrent_users: int,
        bandwidth_mbps: int,
    ) -> OrganizationLimits:
        """Update *organization_id*'s resource limits."""
        limits = await self.get_or_create(organization_id)
        limits.cpu_cores = cpu_cores
        limits.memory_mb = memory_mb
        limits.storage_gb = storage_gb
        limits.queue_usage = queue_usage
        limits.concurrent_workflows = concurrent_workflows
        limits.concurrent_jobs = concurrent_jobs
        limits.concurrent_ai_tasks = concurrent_ai_tasks
        limits.concurrent_users = concurrent_users
        limits.bandwidth_mbps = bandwidth_mbps
        return limits


__all__ = ["OrganizationLimitsService"]
