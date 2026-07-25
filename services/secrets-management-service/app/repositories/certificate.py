"""Repository for :class:`app.models.certificate.Certificate`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.certificate import Certificate
from app.models.enums import CertificateStatus


class CertificateRepository(BaseRepository[Certificate]):
    """CRUD plus lookup for :class:`Certificate`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, Certificate, tenant_scope=tenant_scope)

    async def get_by_fingerprint(self, fingerprint: str) -> Certificate | None:
        """Return the certificate identified by *fingerprint*, or ``None``."""
        stmt = self._base_select().where(Certificate.fingerprint == fingerprint)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_org(self, organization_id: UUID) -> list[Certificate]:
        """Every certificate belonging to *organization_id*."""
        stmt = self._base_select().where(Certificate.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_expiring_before(self, cutoff: datetime) -> list[Certificate]:
        """Every non-expired, non-revoked certificate expiring before *cutoff*
        ("Expiration Tracking")."""
        stmt = (
            self._base_select()
            .where(
                Certificate.status == CertificateStatus.VALID,
                Certificate.not_after < cutoff,
            )
            .order_by(asc(Certificate.not_after))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["CertificateRepository"]
