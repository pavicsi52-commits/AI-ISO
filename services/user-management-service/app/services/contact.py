"""User contact method management."""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.not_found import NotFoundError

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.contact import UserContact
from app.models.enums import ContactType
from app.repositories.contact import UserContactRepository


class UserContactService:
    """Creates, lists, and removes additional contact methods for a user."""

    def __init__(self, contacts: UserContactRepository) -> None:
        self._contacts = contacts

    async def add(
        self,
        user_id: UUID,
        *,
        contact_type: ContactType,
        value: str,
        label: str | None,
        is_primary: bool,
    ) -> UserContact:
        """Add a new contact method for *user_id*."""
        return await self._contacts.create(
            UserContact(
                user_id=user_id,
                contact_type=contact_type,
                value=value,
                label=label,
                is_primary=is_primary,
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )

    async def list_for_user(self, user_id: UUID) -> list[UserContact]:
        """Every additional contact method on record for *user_id*."""
        return await self._contacts.list_for_user(user_id)

    async def remove(self, user_id: UUID, contact_id: UUID) -> None:
        """Remove *user_id*'s contact method with id *contact_id*.

        Raises:
            NotFoundError: If no such contact method belongs to *user_id*.
        """
        record = await self._contacts.require_by_id(contact_id)
        if record.user_id != user_id:
            raise NotFoundError(f"Contact '{contact_id}' was not found.")
        await self._contacts.delete(contact_id)


__all__ = ["UserContactService"]
