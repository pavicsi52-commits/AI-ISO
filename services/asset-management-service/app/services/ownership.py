"""Asset ownership and contact management. Per docs/038 "OWNERSHIP":
Business Owner, Technical Owner, Application Owner, Infrastructure
Owner, Department, Support Team, Vendor Contact, Escalation Contact,
Ownership History, Transfer Ownership.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from shared_core.events.base import DomainEvent

from app.events.asset_events import OwnershipTransferredEvent
from app.models.asset_contact import AssetContact
from app.models.asset_owner import AssetOwner
from app.models.enums import ContactRole, OwnerRole
from app.repositories.asset_contact import AssetContactRepository
from app.repositories.asset_owner import AssetOwnerRepository

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class OwnershipService:
    """Transfers ownership roles and manages reachable contacts for a managed asset."""

    def __init__(
        self,
        owners: AssetOwnerRepository,
        contacts: AssetContactRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._owners = owners
        self._contacts = contacts
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def list_owners(self, managed_asset_id: UUID) -> list[AssetOwner]:
        """Every ownership-role assignment on *managed_asset_id* ("Ownership History")."""
        return await self._owners.list_for_managed_asset(managed_asset_id)

    async def list_contacts(self, managed_asset_id: UUID) -> list[AssetContact]:
        """Every reachable contact for *managed_asset_id*."""
        return await self._contacts.list_for_managed_asset(managed_asset_id)

    async def transfer(
        self,
        managed_asset_id: UUID,
        *,
        organization_id: UUID,
        role: OwnerRole,
        principal_id: UUID | None,
        name: str | None,
    ) -> AssetOwner:
        """Transfer (or first-assign) *managed_asset_id*'s owner for *role*
        ("Transfer Ownership").
        """
        existing = await self._owners.get_for_role(managed_asset_id, role)
        if existing is not None:
            existing.principal_id = principal_id
            existing.name = name
            owner = existing
        else:
            owner = await self._owners.create(
                AssetOwner(
                    managed_asset_id=managed_asset_id,
                    organization_id=organization_id,
                    role=role,
                    principal_id=principal_id,
                    name=name,
                )
            )
        await self._publish(
            OwnershipTransferredEvent(
                source_service="asset-management-service",
                payload={"managed_asset_id": str(managed_asset_id), "role": str(role)},
            )
        )
        return owner

    async def assign_contact(
        self,
        managed_asset_id: UUID,
        *,
        organization_id: UUID,
        role: ContactRole,
        name: str,
        email: str | None,
        phone: str | None,
    ) -> AssetContact:
        """Assign (or replace) *managed_asset_id*'s contact for *role*."""
        existing = await self._contacts.get_for_role(managed_asset_id, role)
        if existing is not None:
            existing.name = name
            existing.email = email
            existing.phone = phone
            return existing
        return await self._contacts.create(
            AssetContact(
                managed_asset_id=managed_asset_id,
                organization_id=organization_id,
                role=role,
                name=name,
                email=email,
                phone=phone,
            )
        )


__all__ = ["OwnershipService"]
