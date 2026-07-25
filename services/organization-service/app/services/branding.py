"""Organization branding management. Per docs/033 "BRANDING"."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import OrganizationActivityType
from app.models.organization_branding import OrganizationBranding
from app.repositories.organization_branding import OrganizationBrandingRepository
from app.services.activity import OrganizationActivityService


class OrganizationBrandingService:
    """Reads and updates an organization's white-label branding."""

    def __init__(
        self, branding: OrganizationBrandingRepository, activity: OrganizationActivityService
    ) -> None:
        self._branding = branding
        self._activity = activity

    async def get_or_create(self, organization_id: UUID) -> OrganizationBranding:
        """Return *organization_id*'s branding, creating defaults if they don't exist yet."""
        existing = await self._branding.get_for_org(organization_id)
        if existing is not None:
            return existing
        return await self._branding.create(OrganizationBranding(organization_id=organization_id))

    async def update(
        self,
        organization_id: UUID,
        *,
        logo_url: str | None,
        dark_logo_url: str | None,
        favicon_url: str | None,
        primary_color: str | None,
        secondary_color: str | None,
        theme: str,
        email_templates: dict[str, Any],
        login_screen_branding: dict[str, Any],
        dashboard_branding: dict[str, Any],
    ) -> OrganizationBranding:
        """Update *organization_id*'s branding ("Branding Changes")."""
        branding = await self.get_or_create(organization_id)
        branding.logo_url = logo_url
        branding.dark_logo_url = dark_logo_url
        branding.favicon_url = favicon_url
        branding.primary_color = primary_color
        branding.secondary_color = secondary_color
        branding.theme = theme
        branding.email_templates = email_templates
        branding.login_screen_branding = login_screen_branding
        branding.dashboard_branding = dashboard_branding
        await self._activity.record(
            organization_id, activity_type=OrganizationActivityType.BRANDING_CHANGED
        )
        return branding


__all__ = ["OrganizationBrandingService"]
