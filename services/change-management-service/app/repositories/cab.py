"""Repositories for CAB reviews and their votes."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cab import ChangeCab, ChangeCabVote


class ChangeCabRepository(BaseRepository[ChangeCab]):
    """Change Advisory Board reviews."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ChangeCab, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, cab_id: UUID) -> ChangeCab:
        """One CAB review by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ChangeCab.organization_id == organization_id)
            .where(ChangeCab.id == cab_id)
        )
        result = await self._session.execute(stmt)
        found: ChangeCab | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No CAB review with id {cab_id} in this organization.")
        return found

    async def get_for_change(self, organization_id: UUID, change_id: UUID) -> ChangeCab | None:
        """The CAB review for one change, if one has been opened."""
        stmt = (
            self._base_select()
            .where(ChangeCab.organization_id == organization_id)
            .where(ChangeCab.change_id == change_id)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


class ChangeCabVoteRepository(BaseRepository[ChangeCabVote]):
    """Individual votes cast at a CAB review."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ChangeCabVote, tenant_scope=tenant_scope)

    async def list_for_cab(self, organization_id: UUID, cab_id: UUID) -> list[ChangeCabVote]:
        """Every vote cast at one review."""
        stmt = (
            self._base_select()
            .where(ChangeCabVote.organization_id == organization_id)
            .where(ChangeCabVote.cab_id == cab_id)
            .order_by(ChangeCabVote.voted_at)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_voter(
        self, organization_id: UUID, cab_id: UUID, voter_id: str
    ) -> ChangeCabVote | None:
        """One member's vote at one review, if they have voted."""
        stmt = (
            self._base_select()
            .where(ChangeCabVote.organization_id == organization_id)
            .where(ChangeCabVote.cab_id == cab_id)
            .where(ChangeCabVote.voter_id == voter_id)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["ChangeCabRepository", "ChangeCabVoteRepository"]
