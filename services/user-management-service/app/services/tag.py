"""User tag management. Per docs/031 "USER TAGS"."""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.tag import UserTag
from app.repositories.tag import UserTagRepository


class UserTagService:
    """Assigns, lists, and removes tags on a user."""

    def __init__(self, tags: UserTagRepository) -> None:
        self._tags = tags

    async def assign(self, user_id: UUID, *, label: str, category: str | None) -> UserTag:
        """Assign *label* to *user_id*.

        Raises:
            ConflictError: If *user_id* already has this exact label.
        """
        existing = await self._tags.get_by_label(user_id, label)
        if existing is not None:
            raise ConflictError(f"User already has tag {label!r}.")
        return await self._tags.create(
            UserTag(
                user_id=user_id,
                label=label,
                category=category,
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )

    async def list_for_user(self, user_id: UUID) -> list[UserTag]:
        """Every tag assigned to *user_id*."""
        return await self._tags.list_for_user(user_id)

    async def remove(self, user_id: UUID, tag_id: UUID) -> None:
        """Remove *user_id*'s tag with id *tag_id*.

        Raises:
            NotFoundError: If no such tag assignment belongs to *user_id*.
        """
        record = await self._tags.require_by_id(tag_id)
        if record.user_id != user_id:
            raise NotFoundError(f"Tag '{tag_id}' was not found.")
        await self._tags.delete(tag_id)


__all__ = ["UserTagService"]
