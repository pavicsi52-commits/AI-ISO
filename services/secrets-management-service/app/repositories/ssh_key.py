"""Repository for :class:`app.models.ssh_key.SSHKey`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ssh_key import SSHKey


class SSHKeyRepository(BaseRepository[SSHKey]):
    """CRUD plus lookup for :class:`SSHKey`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, SSHKey, tenant_scope=tenant_scope)

    async def get_by_fingerprint(self, fingerprint: str) -> SSHKey | None:
        """Return the SSH key identified by *fingerprint*, or ``None``."""
        stmt = self._base_select().where(SSHKey.fingerprint == fingerprint)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_org(self, organization_id: UUID) -> list[SSHKey]:
        """Every SSH key belonging to *organization_id*."""
        stmt = self._base_select().where(SSHKey.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["SSHKeyRepository"]
