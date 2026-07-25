"""License management. Per docs/033 "LICENSE MANAGEMENT": Track,
Activation, Validation.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from shared_core.events.base import DomainEvent

from app.events.organization_events import LicenseExpiredEvent
from app.models.enums import LicenseStatus, OrganizationActivityType
from app.models.organization_license import OrganizationLicense
from app.repositories.organization_license import OrganizationLicenseRepository
from app.services.activity import OrganizationActivityService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class OrganizationLicenseService:
    """Reads, updates, and validates an organization's license."""

    def __init__(
        self,
        licenses: OrganizationLicenseRepository,
        activity: OrganizationActivityService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._licenses = licenses
        self._activity = activity
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_or_create(self, organization_id: UUID) -> OrganizationLicense:
        """Return *organization_id*'s license, creating a pending one if missing."""
        existing = await self._licenses.get_for_org(organization_id)
        if existing is not None:
            return await self._validate(existing)
        created = await self._licenses.create(
            OrganizationLicense(
                organization_id=organization_id,
                license_key=f"PENDING-{organization_id}",
            )
        )
        return created

    async def update(
        self,
        organization_id: UUID,
        *,
        license_type: str,
        license_key: str,
        seat_count: int,
        expires_at: datetime | None,
        grace_period_days: int,
    ) -> OrganizationLicense:
        """Update *organization_id*'s license ("License Changes")."""
        license_ = await self.get_or_create(organization_id)
        license_.license_type = license_type
        license_.license_key = license_key
        license_.seat_count = seat_count
        license_.expires_at = expires_at
        license_.grace_period_days = grace_period_days
        license_.status = LicenseStatus.ACTIVE
        license_.activated_at = license_.activated_at or datetime.now(UTC)
        await self._activity.record(
            organization_id, activity_type=OrganizationActivityType.LICENSE_CHANGED
        )
        return license_

    async def _validate(self, license_: OrganizationLicense) -> OrganizationLicense:
        """Transition an expired license's status, publishing ``LicenseExpired`` once."""
        if license_.expires_at is None:
            return license_
        now = datetime.now(UTC)
        current_status = LicenseStatus(str(license_.status))
        if now <= license_.expires_at or current_status == LicenseStatus.EXPIRED:
            return license_
        license_.status = LicenseStatus.EXPIRED
        await self._publish(
            LicenseExpiredEvent(
                source_service="organization-service",
                payload={"organization_id": str(license_.organization_id)},
            )
        )
        return license_


__all__ = ["OrganizationLicenseService"]
