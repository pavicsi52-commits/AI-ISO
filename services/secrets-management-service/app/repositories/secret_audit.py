"""Repository for :class:`app.models.secret_audit.SecretAuditEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.secret_audit import SecretAuditEntry


class SecretAuditRepository(BaseRepository[SecretAuditEntry]):
    """CRUD plus lookup for :class:`SecretAuditEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, SecretAuditEntry, tenant_scope=tenant_scope)

    async def list_for_secret(self, secret_id: UUID) -> list[SecretAuditEntry]:
        """Every audit entry for *secret_id*, newest first."""
        stmt = (
            self._base_select()
            .where(SecretAuditEntry.secret_id == secret_id)
            .order_by(desc(SecretAuditEntry.created_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["SecretAuditRepository"]
