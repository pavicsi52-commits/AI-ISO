"""Quota management. Per docs/033 "QUOTAS": Configurable per organization."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from shared_core.events.base import DomainEvent

from app.events.organization_events import QuotaExceededEvent
from app.models.enums import OrganizationActivityType
from app.models.organization_quota import OrganizationQuota
from app.quotas.enforcement import QuotaCheckResult, check_quota
from app.repositories.member import OrganizationMemberRepository
from app.repositories.organization_quota import OrganizationQuotaRepository
from app.services.activity import OrganizationActivityService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class OrganizationQuotaService:
    """Reads, updates, and enforces an organization's quotas."""

    def __init__(
        self,
        quotas: OrganizationQuotaRepository,
        members: OrganizationMemberRepository,
        activity: OrganizationActivityService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._quotas = quotas
        self._members = members
        self._activity = activity
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_or_create(self, organization_id: UUID) -> OrganizationQuota:
        """Return *organization_id*'s quotas, creating defaults if they don't exist yet."""
        existing = await self._quotas.get_for_org(organization_id)
        if existing is not None:
            return existing
        return await self._quotas.create(OrganizationQuota(organization_id=organization_id))

    async def update(
        self,
        organization_id: UUID,
        *,
        max_users: int,
        max_projects: int,
        max_assets: int,
        max_storage_gb: int,
        max_workflows: int,
        max_automation_jobs: int,
        max_connectors: int,
        max_api_calls_per_day: int,
        max_ai_requests_per_day: int,
        max_plugins: int,
    ) -> OrganizationQuota:
        """Update *organization_id*'s quotas ("Quota Changes")."""
        quota = await self.get_or_create(organization_id)
        quota.max_users = max_users
        quota.max_projects = max_projects
        quota.max_assets = max_assets
        quota.max_storage_gb = max_storage_gb
        quota.max_workflows = max_workflows
        quota.max_automation_jobs = max_automation_jobs
        quota.max_connectors = max_connectors
        quota.max_api_calls_per_day = max_api_calls_per_day
        quota.max_ai_requests_per_day = max_ai_requests_per_day
        quota.max_plugins = max_plugins
        await self._activity.record(
            organization_id, activity_type=OrganizationActivityType.QUOTA_CHANGED
        )
        return quota

    async def check_user_quota(self, organization_id: UUID) -> QuotaCheckResult:
        """Check current member count against ``max_users`` ("Enforce quotas").

        Publishes ``QuotaExceeded`` the moment the check fails.
        """
        quota = await self.get_or_create(organization_id)
        current = await self._members.count_for_org(organization_id)
        result = check_quota(current=current, maximum=quota.max_users)
        if not result.within_quota:
            await self._activity.record(
                organization_id, activity_type=OrganizationActivityType.QUOTA_EXCEEDED
            )
            await self._publish(
                QuotaExceededEvent(
                    source_service="organization-service",
                    payload={"organization_id": str(organization_id), "quota": "max_users"},
                )
            )
        return result


__all__ = ["OrganizationQuotaService"]
