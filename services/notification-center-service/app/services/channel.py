"""Per-organization channel configuration."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.channel import NotificationChannelConfig
from app.models.enums import NotificationChannelKind
from app.repositories.channel import NotificationChannelConfigRepository


class ChannelConfigService:
    """Which channels an organization has enabled, and their configuration."""

    def __init__(self, channels: NotificationChannelConfigRepository) -> None:
        self._channels = channels

    async def set_config(
        self,
        organization_id: UUID,
        channel: NotificationChannelKind,
        *,
        enabled: bool = True,
        config: dict[str, Any] | None = None,
        description: str | None = None,
    ) -> NotificationChannelConfig:
        """Create or replace this organization's configuration for *channel*."""
        existing = await self._channels.get_by_channel(organization_id, channel)
        if existing is None:
            return await self._channels.create(
                NotificationChannelConfig(
                    organization_id=organization_id,
                    channel=channel,
                    enabled=enabled,
                    config=dict(config or {}),
                    description=description,
                )
            )
        existing.enabled = enabled
        existing.config = dict(config or {})
        if description is not None:
            existing.description = description
        return await self._channels.update(existing)

    async def get_config(
        self, organization_id: UUID, channel: NotificationChannelKind
    ) -> NotificationChannelConfig | None:
        """This organization's own configuration for *channel*, if any."""
        return await self._channels.get_by_channel(organization_id, channel)

    async def list_configs(self, organization_id: UUID) -> list[NotificationChannelConfig]:
        """Every channel this organization has configured."""
        return await self._channels.list_for_org(organization_id)

    async def is_enabled(self, organization_id: UUID, channel: NotificationChannelKind) -> bool:
        """Whether *channel* is configured and enabled for this organization.

        ``EMAIL`` and ``IN_APP`` are always available -- every prior
        AI-IOS service already assumes best-effort email is reachable
        (``shared_core.notifications.factory`` auto-registers it from
        `EmailSettings`), and in-app delivery is this service's own
        always-on notification feed, needing no external configuration.
        Every other channel needs an explicit, organization-owned
        configuration row before it is ever dispatched to.
        """
        if channel in (NotificationChannelKind.EMAIL, NotificationChannelKind.IN_APP):
            return True
        config = await self.get_config(organization_id, channel)
        return config is not None and config.enabled


__all__ = ["ChannelConfigService"]
