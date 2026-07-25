"""User address management."""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.not_found import NotFoundError

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.address import UserAddress
from app.models.enums import AddressType
from app.repositories.address import UserAddressRepository


class UserAddressService:
    """Creates, lists, and removes addresses for a user."""

    def __init__(self, addresses: UserAddressRepository) -> None:
        self._addresses = addresses

    async def add(
        self,
        user_id: UUID,
        *,
        address_type: AddressType,
        line1: str,
        line2: str | None,
        city: str | None,
        state_province: str | None,
        postal_code: str | None,
        country: str | None,
        is_primary: bool,
    ) -> UserAddress:
        """Add a new address for *user_id*."""
        return await self._addresses.create(
            UserAddress(
                user_id=user_id,
                address_type=address_type,
                line1=line1,
                line2=line2,
                city=city,
                state_province=state_province,
                postal_code=postal_code,
                country=country,
                is_primary=is_primary,
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )

    async def list_for_user(self, user_id: UUID) -> list[UserAddress]:
        """Every address on record for *user_id*."""
        return await self._addresses.list_for_user(user_id)

    async def remove(self, user_id: UUID, address_id: UUID) -> None:
        """Remove *user_id*'s address with id *address_id*.

        Raises:
            NotFoundError: If no such address belongs to *user_id*.
        """
        record = await self._addresses.require_by_id(address_id)
        if record.user_id != user_id:
            raise NotFoundError(f"Address '{address_id}' was not found.")
        await self._addresses.delete(address_id)


__all__ = ["UserAddressService"]
