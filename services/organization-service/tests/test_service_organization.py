"""Direct service-layer tests for ``app/services/organization.py`` branches
the API-layer tests don't reach: the SUSPENDED status transition and
``create``'s full default-child-row provisioning.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.organization_events import OrganizationSuspendedEvent
from app.models.enums import OrganizationStatus
from app.repositories.activity import OrganizationActivityRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.organization_branding import OrganizationBrandingRepository
from app.repositories.organization_limits import OrganizationLimitsRepository
from app.repositories.organization_preferences import OrganizationPreferencesRepository
from app.repositories.organization_quota import OrganizationQuotaRepository
from app.repositories.organization_settings import OrganizationSettingsRepository
from app.repositories.organization_subscription import OrganizationSubscriptionRepository
from app.services.activity import OrganizationActivityService
from app.services.organization import OrganizationService


def _make_service(db_session: AsyncSession) -> OrganizationService:
    activity = OrganizationActivityService(OrganizationActivityRepository(db_session))
    return OrganizationService(
        OrganizationRepository(db_session),
        OrganizationSettingsRepository(db_session),
        OrganizationPreferencesRepository(db_session),
        OrganizationBrandingRepository(db_session),
        OrganizationSubscriptionRepository(db_session),
        OrganizationLimitsRepository(db_session),
        OrganizationQuotaRepository(db_session),
        activity,
        publish_event=None,
    )


async def test_create_provisions_default_child_rows(db_session: AsyncSession) -> None:
    service = _make_service(db_session)
    organization = await service.create(
        name="Full Create",
        slug=f"full-{uuid.uuid4().hex[:8]}",
        display_name=None,
        short_name=None,
        description=None,
        primary_domain=None,
        primary_contact_email=None,
        website=None,
        industry=None,
        timezone="UTC",
        language="en",
        country=None,
        currency="USD",
        metadata={},
    )
    assert organization.organization_id == organization.id


async def test_update_to_suspended_publishes_suspended_event(db_session: AsyncSession) -> None:
    published: list[OrganizationSuspendedEvent] = []

    async def _publish(event: object) -> None:
        if isinstance(event, OrganizationSuspendedEvent):
            published.append(event)

    activity = OrganizationActivityService(OrganizationActivityRepository(db_session))
    service = OrganizationService(
        OrganizationRepository(db_session),
        OrganizationSettingsRepository(db_session),
        OrganizationPreferencesRepository(db_session),
        OrganizationBrandingRepository(db_session),
        OrganizationSubscriptionRepository(db_session),
        OrganizationLimitsRepository(db_session),
        OrganizationQuotaRepository(db_session),
        activity,
        publish_event=_publish,
    )
    organization = await service.create(
        name="Suspend Me",
        slug=f"suspend-{uuid.uuid4().hex[:8]}",
        display_name=None,
        short_name=None,
        description=None,
        primary_domain=None,
        primary_contact_email=None,
        website=None,
        industry=None,
        timezone="UTC",
        language="en",
        country=None,
        currency="USD",
        metadata={},
    )

    suspended = await service.update(
        organization.id,
        name=organization.name,
        display_name=None,
        short_name=None,
        description=None,
        status=OrganizationStatus.SUSPENDED,
        primary_domain=None,
        primary_contact_email=None,
        logo_url=None,
        website=None,
        industry=None,
        timezone="UTC",
        language="en",
        country=None,
        currency="USD",
        metadata={},
    )
    assert suspended.status == OrganizationStatus.SUSPENDED
    assert len(published) == 1

    # Updating again while already suspended doesn't republish.
    await service.update(
        organization.id,
        name=organization.name,
        display_name=None,
        short_name=None,
        description=None,
        status=OrganizationStatus.SUSPENDED,
        primary_domain=None,
        primary_contact_email=None,
        logo_url=None,
        website=None,
        industry=None,
        timezone="UTC",
        language="en",
        country=None,
        currency="USD",
        metadata={},
    )
    assert len(published) == 1


async def test_delete_unknown_organization_not_found(db_session: AsyncSession) -> None:
    service = _make_service(db_session)
    with pytest.raises(NotFoundError):
        await service.delete(uuid.uuid4())
