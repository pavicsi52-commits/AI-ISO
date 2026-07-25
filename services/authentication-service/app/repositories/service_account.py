"""Repository for :class:`app.models.service_account.ServiceAccount`."""

from __future__ import annotations

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.service_account import ServiceAccount


class ServiceAccountRepository(BaseRepository[ServiceAccount]):
    """CRUD plus lookup for :class:`ServiceAccount`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ServiceAccount, tenant_scope=tenant_scope)

    async def get_by_hashed_token(self, hashed_token: str) -> ServiceAccount | None:
        """Return the service account with this hashed token value, or ``None``."""
        stmt = self._base_select().where(ServiceAccount.hashed_token == hashed_token)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> ServiceAccount | None:
        """Return the service account with this name, or ``None``."""
        stmt = self._base_select().where(ServiceAccount.name == name)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["ServiceAccountRepository"]
