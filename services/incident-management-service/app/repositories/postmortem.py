"""Repositories for postmortems and their action items."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ActionItemStatus
from app.models.postmortem import Postmortem, PostmortemActionItem


class PostmortemRepository(BaseRepository[Postmortem]):
    """Post-incident review documents."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, Postmortem, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, postmortem_id: UUID) -> Postmortem:
        """One postmortem by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(Postmortem.organization_id == organization_id)
            .where(Postmortem.id == postmortem_id)
        )
        result = await self._session.execute(stmt)
        found: Postmortem | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No postmortem with id {postmortem_id} in this organization.")
        return found

    async def get_for_incident(self, organization_id: UUID, incident_id: UUID) -> Postmortem | None:
        """The postmortem for one incident, if one has been started."""
        stmt = (
            self._base_select()
            .where(Postmortem.organization_id == organization_id)
            .where(Postmortem.incident_id == incident_id)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


class ActionItemRepository(BaseRepository[PostmortemActionItem]):
    """Postmortem action items."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PostmortemActionItem, tenant_scope=tenant_scope)

    async def require_in_org(
        self, organization_id: UUID, action_item_id: UUID
    ) -> PostmortemActionItem:
        """One action item by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(PostmortemActionItem.organization_id == organization_id)
            .where(PostmortemActionItem.id == action_item_id)
        )
        result = await self._session.execute(stmt)
        found: PostmortemActionItem | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No action item with id {action_item_id} in this organization.")
        return found

    async def list_for_postmortem(
        self, organization_id: UUID, postmortem_id: UUID
    ) -> list[PostmortemActionItem]:
        """Every action item committed in one postmortem."""
        stmt = (
            self._base_select()
            .where(PostmortemActionItem.organization_id == organization_id)
            .where(PostmortemActionItem.postmortem_id == postmortem_id)
            .order_by(PostmortemActionItem.due_at)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_open_for_owner(
        self, organization_id: UUID, owner_id: str, *, limit: int = 200
    ) -> list[PostmortemActionItem]:
        """One person's outstanding commitments across every postmortem."""
        stmt = (
            self._base_select()
            .where(PostmortemActionItem.organization_id == organization_id)
            .where(PostmortemActionItem.owner_id == owner_id)
            .where(
                PostmortemActionItem.status.in_(
                    [str(ActionItemStatus.OPEN), str(ActionItemStatus.IN_PROGRESS)]
                )
            )
            .order_by(PostmortemActionItem.due_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ActionItemRepository", "PostmortemRepository"]
