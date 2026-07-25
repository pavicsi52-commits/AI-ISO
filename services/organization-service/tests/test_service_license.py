"""Direct service-layer tests for ``app/services/license.py``'s expiry
transition, not reachable through the API-layer tests alone.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import make_org

from app.events.organization_events import LicenseExpiredEvent
from app.models.enums import LicenseStatus
from app.repositories.activity import OrganizationActivityRepository
from app.repositories.organization_license import OrganizationLicenseRepository
from app.services.activity import OrganizationActivityService
from app.services.license import OrganizationLicenseService


async def test_get_or_create_with_no_expiry_stays_pending(db_session: AsyncSession) -> None:
    organization = await make_org(db_session)
    activity = OrganizationActivityService(OrganizationActivityRepository(db_session))
    service = OrganizationLicenseService(OrganizationLicenseRepository(db_session), activity)

    license_ = await service.get_or_create(organization.id)
    assert license_.status == LicenseStatus.PENDING_ACTIVATION

    # Calling again with still-no expiry is a no-op re: status.
    again = await service.get_or_create(organization.id)
    assert again.status == LicenseStatus.PENDING_ACTIVATION


async def test_expired_license_transitions_and_publishes_once(db_session: AsyncSession) -> None:
    organization = await make_org(db_session)
    activity = OrganizationActivityService(OrganizationActivityRepository(db_session))
    published: list[LicenseExpiredEvent] = []

    async def _publish(event: object) -> None:
        if isinstance(event, LicenseExpiredEvent):
            published.append(event)

    service = OrganizationLicenseService(
        OrganizationLicenseRepository(db_session), activity, publish_event=_publish
    )
    await service.update(
        organization.id,
        license_type="standard",
        license_key="KEY-1",
        seat_count=5,
        expires_at=datetime.now(UTC) - timedelta(days=1),
        grace_period_days=0,
    )

    first_check = await service.get_or_create(organization.id)
    assert first_check.status == LicenseStatus.EXPIRED
    assert len(published) == 1

    # A second check on an already-expired license doesn't republish.
    second_check = await service.get_or_create(organization.id)
    assert second_check.status == LicenseStatus.EXPIRED
    assert len(published) == 1


async def test_active_unexpired_license_unaffected(db_session: AsyncSession) -> None:
    organization = await make_org(db_session)
    activity = OrganizationActivityService(OrganizationActivityRepository(db_session))
    service = OrganizationLicenseService(OrganizationLicenseRepository(db_session), activity)
    await service.update(
        organization.id,
        license_type="standard",
        license_key="KEY-2",
        seat_count=5,
        expires_at=datetime.now(UTC) + timedelta(days=30),
        grace_period_days=14,
    )

    checked = await service.get_or_create(organization.id)
    assert checked.status == LicenseStatus.ACTIVE
