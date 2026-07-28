"""Repository for :class:`app.models.ai_memory.AiMemory`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_memory import AiMemory
from app.models.enums import MemoryScope


class AiMemoryRepository(BaseRepository[AiMemory]):
    """CRUD plus lookup for :class:`AiMemory`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AiMemory, tenant_scope=tenant_scope)

    async def list_live(
        self, organization_id: UUID, scope: MemoryScope, scope_reference: str, moment: datetime
    ) -> list[AiMemory]:
        """Every unexpired memory in one scope, most important first.

        "Memory Expiration" is enforced here rather than by a cleanup
        job: an expired memory must stop influencing answers the moment
        it expires, not whenever a sweep next happens to run.
        """
        stmt = (
            self._base_select()
            .where(
                AiMemory.organization_id == organization_id,
                AiMemory.scope == scope,
                AiMemory.scope_reference == scope_reference,
                or_(AiMemory.expires_at.is_(None), AiMemory.expires_at > moment),
            )
            .order_by(AiMemory.importance.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_key(
        self, organization_id: UUID, scope: MemoryScope, scope_reference: str, key: str
    ) -> AiMemory | None:
        """Return one remembered fact by key, if present."""
        stmt = self._base_select().where(
            AiMemory.organization_id == organization_id,
            AiMemory.scope == scope,
            AiMemory.scope_reference == scope_reference,
            AiMemory.key == key,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def delete_expired(self, organization_id: UUID, moment: datetime) -> int:
        """Purge memories whose own expiry has passed, returning the count."""
        stmt = self._base_select().where(
            AiMemory.organization_id == organization_id,
            AiMemory.expires_at.is_not(None),
            AiMemory.expires_at <= moment,
        )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        for row in rows:
            await self._session.delete(row)
        await self._session.flush()
        return len(rows)


__all__ = ["AiMemoryRepository"]
