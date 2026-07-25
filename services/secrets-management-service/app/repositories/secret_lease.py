"""Repository for :class:`app.models.secret_lease.SecretLease`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import LeaseStatus
from app.models.secret_lease import SecretLease


class SecretLeaseRepository(BaseRepository[SecretLease]):
    """CRUD plus lookup for :class:`SecretLease`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, SecretLease, tenant_scope=tenant_scope)

    async def list_for_secret(self, secret_id: UUID) -> list[SecretLease]:
        """Every lease ever issued on *secret_id*, newest first."""
        stmt = (
            self._base_select()
            .where(SecretLease.secret_id == secret_id)
            .order_by(desc(SecretLease.issued_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_active_expired_before(self, cutoff: datetime) -> list[SecretLease]:
        """Every still-``ACTIVE`` lease whose :attr:`expires_at` is before *cutoff*.

        Used by the lease-sweep background task to find leases due for
        automatic expiration.
        """
        stmt = self._base_select().where(
            SecretLease.status == LeaseStatus.ACTIVE, SecretLease.expires_at < cutoff
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["SecretLeaseRepository"]
