"""Organization tag management."""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError

from app.models.tag import OrganizationTag
from app.repositories.tag import OrganizationTagRepository


class OrganizationTagService:
    """Assigns, lists, and removes tags on an organization."""

    def __init__(self, tags: OrganizationTagRepository) -> None:
        self._tags = tags

    async def list_for_org(self, organization_id: UUID) -> list[OrganizationTag]:
        """Every tag assigned to *organization_id*."""
        return await self._tags.list_for_org(organization_id)

    async def assign(
        self, organization_id: UUID, *, label: str, category: str | None
    ) -> OrganizationTag:
        """Assign *label* to *organization_id*.

        Raises:
            ConflictError: If *label* is already assigned.
        """
        if await self._tags.get_by_label(organization_id, label) is not None:
            raise ConflictError(f"Tag {label!r} is already assigned to this organization.")
        return await self._tags.create(
            OrganizationTag(organization_id=organization_id, label=label, category=category)
        )

    async def remove(self, organization_id: UUID, tag_id: UUID) -> None:
        """Remove a tag.

        Raises:
            NotFoundError: If no such tag exists for *organization_id*.
        """
        record = await self._tags.require_by_id(tag_id)
        if record.organization_id != organization_id:
            raise NotFoundError(f"Tag '{tag_id}' was not found for this organization.")
        await self._tags.delete(tag_id)


__all__ = ["OrganizationTagService"]
