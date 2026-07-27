"""Repository for :class:`app.models.playbook_signature.PlaybookSignature`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playbook_signature import PlaybookSignature


class PlaybookSignatureRepository(BaseRepository[PlaybookSignature]):
    """CRUD plus lookup for :class:`PlaybookSignature`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PlaybookSignature, tenant_scope=tenant_scope)

    async def list_for_version(self, version_id: UUID) -> list[PlaybookSignature]:
        """Every signature recorded for *version_id*."""
        stmt = self._base_select().where(PlaybookSignature.version_id == version_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["PlaybookSignatureRepository"]
