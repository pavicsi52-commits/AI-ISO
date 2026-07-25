"""Business unit management. Per docs/033 "BUSINESS UNITS": CRUD,
Hierarchy, Business Unit Owner, Metadata.

No dedicated REST surface is named for business units in docs/033's own
endpoint list (only departments and teams have one) -- this service
exists so the data model is fully usable programmatically, matching
``services/rbac-service``'s identical scope decision for
``resource_permissions``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.business_unit import BusinessUnit
from app.repositories.business_unit import BusinessUnitRepository


class BusinessUnitService:
    """Creates, updates, deletes, and lists business units within an organization."""

    def __init__(self, business_units: BusinessUnitRepository) -> None:
        self._business_units = business_units

    async def get_by_id(self, business_unit_id: UUID) -> BusinessUnit:
        """Return the business unit identified by *business_unit_id*.

        Raises:
            NotFoundError: If no such business unit exists.
        """
        return await self._business_units.require_by_id(business_unit_id)

    async def list_for_org(self, organization_id: UUID) -> list[BusinessUnit]:
        """Every business unit in *organization_id*."""
        return await self._business_units.list_for_org(organization_id)

    async def create(
        self,
        organization_id: UUID,
        *,
        name: str,
        code: str,
        description: str | None,
        parent_business_unit_id: UUID | None,
        owner_id: UUID | None,
        metadata: dict[str, Any],
    ) -> BusinessUnit:
        """Create a new business unit ("Create")."""
        if parent_business_unit_id is not None:
            await self._business_units.require_by_id(parent_business_unit_id)
        return await self._business_units.create(
            BusinessUnit(
                organization_id=organization_id,
                name=name,
                code=code,
                description=description,
                parent_business_unit_id=parent_business_unit_id,
                owner_id=owner_id,
                metadata_=metadata,
            )
        )

    async def delete(self, business_unit_id: UUID) -> None:
        """Delete a business unit ("Delete")."""
        await self.get_by_id(business_unit_id)
        await self._business_units.delete(business_unit_id)


__all__ = ["BusinessUnitService"]
