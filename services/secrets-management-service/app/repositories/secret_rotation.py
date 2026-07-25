"""Repository for :class:`app.models.secret_rotation.SecretRotationEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.secret_rotation import SecretRotationEntry


class SecretRotationRepository(BaseRepository[SecretRotationEntry]):
    """CRUD plus lookup for :class:`SecretRotationEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, SecretRotationEntry, tenant_scope=tenant_scope)

    async def list_for_secret(self, secret_id: UUID) -> list[SecretRotationEntry]:
        """Every rotation attempt for *secret_id*, newest first ("Rotation History")."""
        stmt = (
            self._base_select()
            .where(SecretRotationEntry.secret_id == secret_id)
            .order_by(desc(SecretRotationEntry.rotated_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["SecretRotationRepository"]
