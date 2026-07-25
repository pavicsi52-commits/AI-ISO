"""Repository for :class:`app.models.trusted_device.TrustedDevice`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trusted_device import TrustedDevice


class TrustedDeviceRepository(BaseRepository[TrustedDevice]):
    """CRUD plus lookup/listing for :class:`TrustedDevice`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, TrustedDevice, tenant_scope=tenant_scope)

    async def get_by_fingerprint(
        self, user_id: UUID, device_fingerprint: str
    ) -> TrustedDevice | None:
        """Return *user_id*'s device row matching *device_fingerprint*, or ``None``."""
        stmt = self._base_select().where(
            TrustedDevice.user_id == user_id,
            TrustedDevice.device_fingerprint == device_fingerprint,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: UUID) -> list[TrustedDevice]:
        """Every device on record for *user_id* ("GET /auth/devices")."""
        stmt = self._base_select().where(TrustedDevice.user_id == user_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["TrustedDeviceRepository"]
