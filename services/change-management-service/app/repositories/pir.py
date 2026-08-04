"""Repositories for post-implementation reviews and their action items."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ChangeTaskStatus
from app.models.pir import ChangePostReview, ChangePostReviewActionItem


class ChangePostReviewRepository(BaseRepository[ChangePostReview]):
    """Post-implementation review documents."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ChangePostReview, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, review_id: UUID) -> ChangePostReview:
        """One review by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ChangePostReview.organization_id == organization_id)
            .where(ChangePostReview.id == review_id)
        )
        result = await self._session.execute(stmt)
        found: ChangePostReview | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No post-implementation review with id {review_id} here.")
        return found

    async def get_for_change(
        self, organization_id: UUID, change_id: UUID
    ) -> ChangePostReview | None:
        """The review for one change, if one has been started."""
        stmt = (
            self._base_select()
            .where(ChangePostReview.organization_id == organization_id)
            .where(ChangePostReview.change_id == change_id)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


class ChangePostReviewActionItemRepository(BaseRepository[ChangePostReviewActionItem]):
    """PIR follow-up action items."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ChangePostReviewActionItem, tenant_scope=tenant_scope)

    async def require_in_org(
        self, organization_id: UUID, action_item_id: UUID
    ) -> ChangePostReviewActionItem:
        """One action item by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ChangePostReviewActionItem.organization_id == organization_id)
            .where(ChangePostReviewActionItem.id == action_item_id)
        )
        result = await self._session.execute(stmt)
        found: ChangePostReviewActionItem | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No action item with id {action_item_id} in this organization.")
        return found

    async def list_for_review(
        self, organization_id: UUID, post_review_id: UUID
    ) -> list[ChangePostReviewActionItem]:
        """Every action item committed in one review."""
        stmt = (
            self._base_select()
            .where(ChangePostReviewActionItem.organization_id == organization_id)
            .where(ChangePostReviewActionItem.post_review_id == post_review_id)
            .order_by(ChangePostReviewActionItem.due_at)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_open_for_owner(
        self, organization_id: UUID, owner_id: str, *, limit: int = 200
    ) -> list[ChangePostReviewActionItem]:
        """One person's outstanding commitments across every PIR."""
        stmt = (
            self._base_select()
            .where(ChangePostReviewActionItem.organization_id == organization_id)
            .where(ChangePostReviewActionItem.owner_id == owner_id)
            .where(
                ChangePostReviewActionItem.status.in_(
                    [str(ChangeTaskStatus.PENDING), str(ChangeTaskStatus.IN_PROGRESS)]
                )
            )
            .order_by(ChangePostReviewActionItem.due_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ChangePostReviewActionItemRepository", "ChangePostReviewRepository"]
