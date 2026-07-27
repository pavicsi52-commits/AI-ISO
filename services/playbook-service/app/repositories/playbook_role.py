"""Repository for :class:`app.models.playbook_role.PlaybookRole`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playbook_role import PlaybookRole


class PlaybookRoleRepository(BaseRepository[PlaybookRole]):
    """CRUD plus lookup for :class:`PlaybookRole`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PlaybookRole, tenant_scope=tenant_scope)

    async def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookRole]:
        """Every Ansible role *playbook_id* references."""
        stmt = self._base_select().where(PlaybookRole.playbook_id == playbook_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["PlaybookRoleRepository"]
