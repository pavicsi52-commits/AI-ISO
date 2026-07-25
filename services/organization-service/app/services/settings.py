"""Organization settings management. Per docs/033 "ORGANIZATION SETTINGS"."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import OrganizationActivityType
from app.models.organization_settings import OrganizationSettings
from app.repositories.organization_settings import OrganizationSettingsRepository
from app.services.activity import OrganizationActivityService


class OrganizationSettingsService:
    """Reads and updates an organization's settings."""

    def __init__(
        self, settings: OrganizationSettingsRepository, activity: OrganizationActivityService
    ) -> None:
        self._settings = settings
        self._activity = activity

    async def get_or_create(self, organization_id: UUID) -> OrganizationSettings:
        """Return *organization_id*'s settings, creating defaults if they don't exist yet."""
        existing = await self._settings.get_for_org(organization_id)
        if existing is not None:
            return existing
        return await self._settings.create(OrganizationSettings(organization_id=organization_id))

    async def update(
        self,
        organization_id: UUID,
        *,
        password_policy: dict[str, Any],
        mfa_enforced: bool,
        allowed_domains: list[str],
        default_language: str,
        default_timezone: str,
        session_timeout_minutes: int,
        data_retention_days: int,
        storage_policy: dict[str, Any],
        notification_policy: dict[str, Any],
    ) -> OrganizationSettings:
        """Update *organization_id*'s settings ("Settings Changes")."""
        settings = await self.get_or_create(organization_id)
        settings.password_policy = password_policy
        settings.mfa_enforced = mfa_enforced
        settings.allowed_domains = allowed_domains
        settings.default_language = default_language
        settings.default_timezone = default_timezone
        settings.session_timeout_minutes = session_timeout_minutes
        settings.data_retention_days = data_retention_days
        settings.storage_policy = storage_policy
        settings.notification_policy = notification_policy
        await self._activity.record(
            organization_id, activity_type=OrganizationActivityType.SETTINGS_CHANGED
        )
        return settings


__all__ = ["OrganizationSettingsService"]
