"""The notification channel configuration repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import NotificationChannelConfig
from app.models.enums import NotificationChannelKind


class NotificationChannelConfigRepository(BaseRepository[NotificationChannelConfig]):
    """One organization's own per-channel configuration."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, NotificationChannelConfig, tenant_scope=tenant_scope)

    async def require_in_org(
        self, organization_id: UUID, config_id: UUID
    ) -> NotificationChannelConfig:
        """One channel configuration by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(NotificationChannelConfig.organization_id == organization_id)
            .where(NotificationChannelConfig.id == config_id)
        )
        result = await self._session.execute(stmt)
        found: NotificationChannelConfig | None = result.scalars().first()
        if found is None:
            raise NotFoundError(
                f"No channel configuration with id {config_id} in this organization."
            )
        return found

    async def get_by_channel(
        self, organization_id: UUID, channel: NotificationChannelKind
    ) -> NotificationChannelConfig | None:
        """The configuration row for one channel, if any."""
        stmt = (
            self._base_select()
            .where(NotificationChannelConfig.organization_id == organization_id)
            .where(NotificationChannelConfig.channel == str(channel))
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_org(self, organization_id: UUID) -> list[NotificationChannelConfig]:
        """Every channel this organization has configured."""
        stmt = self._base_select().where(
            NotificationChannelConfig.organization_id == organization_id
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["NotificationChannelConfigRepository"]
