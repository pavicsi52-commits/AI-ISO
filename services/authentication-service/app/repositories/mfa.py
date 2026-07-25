"""Repository for :class:`app.models.mfa.MfaDevice`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mfa import MfaDevice


class MfaDeviceRepository(BaseRepository[MfaDevice]):
    """CRUD plus per-user lookup for :class:`MfaDevice`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, MfaDevice, tenant_scope=tenant_scope)

    async def get_primary_for_user(self, user_id: UUID) -> MfaDevice | None:
        """Return *user_id*'s primary MFA device, or ``None``."""
        stmt = self._base_select().where(
            MfaDevice.user_id == user_id, MfaDevice.is_primary.is_(True)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: UUID) -> list[MfaDevice]:
        """Every MFA device registered to *user_id*."""
        stmt = self._base_select().where(MfaDevice.user_id == user_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["MfaDeviceRepository"]
