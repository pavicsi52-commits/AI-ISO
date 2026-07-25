"""Repository for :class:`app.models.secret_access.SecretAccessGrant`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.secret_access import SecretAccessGrant


class SecretAccessRepository(BaseRepository[SecretAccessGrant]):
    """CRUD plus lookup for :class:`SecretAccessGrant`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, SecretAccessGrant, tenant_scope=tenant_scope)

    async def get_for_principal(
        self, secret_id: UUID, principal_id: UUID
    ) -> SecretAccessGrant | None:
        """Return *principal_id*'s access grant on *secret_id*, or ``None``."""
        stmt = self._base_select().where(
            SecretAccessGrant.secret_id == secret_id,
            SecretAccessGrant.principal_id == principal_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_secret(self, secret_id: UUID) -> list[SecretAccessGrant]:
        """Every access grant on *secret_id*."""
        stmt = self._base_select().where(SecretAccessGrant.secret_id == secret_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["SecretAccessRepository"]
