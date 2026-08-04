"""The notification preference repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import DigestFrequency
from app.models.preference import NotificationPreference


class NotificationPreferenceRepository(BaseRepository[NotificationPreference]):
    """One user's own settings within one organization."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, NotificationPreference, tenant_scope=tenant_scope)

    async def get_for_user(
        self, organization_id: UUID, user_id: str
    ) -> NotificationPreference | None:
        """*user_id*'s stored preferences within this organization, if any."""
        stmt = (
            self._base_select()
            .where(NotificationPreference.organization_id == organization_id)
            .where(NotificationPreference.user_id == user_id)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_digest_subscribers(
        self, *, limit: int = 1_000
    ) -> list[NotificationPreference]:
        """Every user, across every organization, who has opted into a digest.

        Unscoped by organization -- the digest sweep is a single
        leader-elected worker walking every organization's digest
        subscribers in one tick.
        """
        stmt = (
            self._base_select()
            .where(NotificationPreference.digest_frequency != str(DigestFrequency.NONE))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["NotificationPreferenceRepository"]
