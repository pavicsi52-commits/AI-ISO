"""Organization management.

Per docs/033 "ORGANIZATION MODEL"/"ORGANIZATION LIFECYCLE": Create,
Update, Delete, Status transitions. The tenant "root" entity -- its own
``organization_id`` column is set equal to its own ``id`` at creation
(see ``app/constants.py``'s docstring for why), and creating one also
provisions its default settings/preferences/branding/subscription/
license/limits/quota rows, matching the seed migration's own shape for
the default organization.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from shared_core.events.base import DomainEvent
from shared_core.exceptions.conflict import ConflictError

from app.events.organization_events import (
    OrganizationActivatedEvent,
    OrganizationCreatedEvent,
    OrganizationDeletedEvent,
    OrganizationSuspendedEvent,
    OrganizationUpdatedEvent,
)
from app.models.enums import OrganizationActivityType, OrganizationStatus
from app.models.organization import Organization
from app.models.organization_branding import OrganizationBranding
from app.models.organization_limits import OrganizationLimits
from app.models.organization_preferences import OrganizationPreferences
from app.models.organization_quota import OrganizationQuota
from app.models.organization_settings import OrganizationSettings
from app.models.organization_subscription import OrganizationSubscription
from app.repositories.organization import OrganizationRepository
from app.repositories.organization_branding import OrganizationBrandingRepository
from app.repositories.organization_limits import OrganizationLimitsRepository
from app.repositories.organization_preferences import OrganizationPreferencesRepository
from app.repositories.organization_quota import OrganizationQuotaRepository
from app.repositories.organization_settings import OrganizationSettingsRepository
from app.repositories.organization_subscription import OrganizationSubscriptionRepository
from app.services.activity import OrganizationActivityService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class OrganizationService:
    """Creates, updates, deletes, and transitions the status of organizations."""

    def __init__(
        self,
        organizations: OrganizationRepository,
        settings: OrganizationSettingsRepository,
        preferences: OrganizationPreferencesRepository,
        branding: OrganizationBrandingRepository,
        subscriptions: OrganizationSubscriptionRepository,
        limits: OrganizationLimitsRepository,
        quotas: OrganizationQuotaRepository,
        activity: OrganizationActivityService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._organizations = organizations
        self._settings = settings
        self._preferences = preferences
        self._branding = branding
        self._subscriptions = subscriptions
        self._limits = limits
        self._quotas = quotas
        self._activity = activity
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, organization_id: UUID) -> Organization:
        """Return the organization identified by *organization_id*.

        Raises:
            NotFoundError: If no such organization exists.
        """
        return await self._organizations.require_by_id(organization_id)

    async def list_all(self) -> list[Organization]:
        """Every organization ("Organization Management": list)."""
        return await self._organizations.list_all()

    async def create(
        self,
        *,
        name: str,
        slug: str,
        display_name: str | None,
        short_name: str | None,
        description: str | None,
        primary_domain: str | None,
        primary_contact_email: str | None,
        website: str | None,
        industry: str | None,
        timezone: str,
        language: str,
        country: str | None,
        currency: str,
        metadata: dict[str, Any],
    ) -> Organization:
        """Create a new organization, with its default child rows ("Create").

        Raises:
            ConflictError: If *slug* is already taken.
        """
        if await self._organizations.get_by_slug(slug) is not None:
            raise ConflictError(f"Organization slug {slug!r} is already taken.")

        org_id = uuid.uuid4()
        organization = await self._organizations.create(
            Organization(
                id=org_id,
                name=name,
                display_name=display_name,
                short_name=short_name,
                slug=slug,
                description=description,
                status=OrganizationStatus.PENDING,
                primary_domain=primary_domain,
                primary_contact_email=primary_contact_email,
                website=website,
                industry=industry,
                timezone=timezone,
                language=language,
                country=country,
                currency=currency,
                metadata_=metadata,
                organization_id=org_id,
            )
        )
        await self._settings.create(OrganizationSettings(organization_id=org_id))
        await self._preferences.create(OrganizationPreferences(organization_id=org_id))
        await self._branding.create(OrganizationBranding(organization_id=org_id))
        await self._subscriptions.create(OrganizationSubscription(organization_id=org_id))
        await self._limits.create(OrganizationLimits(organization_id=org_id))
        await self._quotas.create(OrganizationQuota(organization_id=org_id))

        await self._activity.record(
            org_id, activity_type=OrganizationActivityType.ORGANIZATION_CREATED
        )
        await self._publish(
            OrganizationCreatedEvent(
                source_service="organization-service",
                payload={"organization_id": str(org_id)},
            )
        )
        return organization

    async def update(
        self,
        organization_id: UUID,
        *,
        name: str,
        display_name: str | None,
        short_name: str | None,
        description: str | None,
        status: OrganizationStatus,
        primary_domain: str | None,
        primary_contact_email: str | None,
        logo_url: str | None,
        website: str | None,
        industry: str | None,
        timezone: str,
        language: str,
        country: str | None,
        currency: str,
        metadata: dict[str, Any],
    ) -> Organization:
        """Replace an organization's mutable fields ("Update")."""
        organization = await self.get_by_id(organization_id)
        previous_status = OrganizationStatus(str(organization.status))
        organization.name = name
        organization.display_name = display_name
        organization.short_name = short_name
        organization.description = description
        organization.status = status
        organization.primary_domain = primary_domain
        organization.primary_contact_email = primary_contact_email
        organization.logo_url = logo_url
        organization.website = website
        organization.industry = industry
        organization.timezone = timezone
        organization.language = language
        organization.country = country
        organization.currency = currency
        organization.metadata_ = metadata

        await self._activity.record(
            organization_id, activity_type=OrganizationActivityType.ORGANIZATION_UPDATED
        )
        await self._publish(
            OrganizationUpdatedEvent(
                source_service="organization-service",
                payload={"organization_id": str(organization_id)},
            )
        )
        if status == OrganizationStatus.ACTIVE and previous_status != OrganizationStatus.ACTIVE:
            await self._activity.record(
                organization_id, activity_type=OrganizationActivityType.ORGANIZATION_ACTIVATED
            )
            await self._publish(
                OrganizationActivatedEvent(
                    source_service="organization-service",
                    payload={"organization_id": str(organization_id)},
                )
            )
        elif (
            status == OrganizationStatus.SUSPENDED
            and previous_status != OrganizationStatus.SUSPENDED
        ):
            await self._activity.record(
                organization_id, activity_type=OrganizationActivityType.ORGANIZATION_SUSPENDED
            )
            await self._publish(
                OrganizationSuspendedEvent(
                    source_service="organization-service",
                    payload={"organization_id": str(organization_id)},
                )
            )
        return organization

    async def delete(self, organization_id: UUID) -> None:
        """Soft-delete an organization ("Delete")."""
        await self.get_by_id(organization_id)
        await self._organizations.delete(organization_id)
        await self._publish(
            OrganizationDeletedEvent(
                source_service="organization-service",
                payload={"organization_id": str(organization_id)},
            )
        )


__all__ = ["OrganizationService"]
