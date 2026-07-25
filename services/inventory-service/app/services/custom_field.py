"""Custom field definition management. Per docs/036 "CUSTOM
ATTRIBUTES": Dynamic Fields, Schemas, Validation, Typed Values.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.conflict import ConflictError

from app.models.asset_custom_field import AssetCustomField
from app.models.enums import CustomFieldType
from app.repositories.asset_custom_field import AssetCustomFieldRepository


class AssetCustomFieldService:
    """Creates and lists custom field definitions for an organization."""

    def __init__(self, fields: AssetCustomFieldRepository) -> None:
        self._fields = fields

    async def list_for_org(self, organization_id: UUID) -> list[AssetCustomField]:
        """Every custom field definition available in *organization_id*."""
        return await self._fields.list_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        name: str,
        description: str | None = None,
        field_type: CustomFieldType = CustomFieldType.STRING,
        is_required: bool = False,
        validation_rule: dict[str, object] | None = None,
    ) -> AssetCustomField:
        """Create a new custom field definition.

        Raises:
            ConflictError: If *name* is already taken within *organization_id*.
        """
        if await self._fields.get_by_name(organization_id, name) is not None:
            raise ConflictError(f"Custom field {name!r} already exists in this organization.")
        return await self._fields.create(
            AssetCustomField(
                organization_id=organization_id,
                name=name,
                description=description,
                field_type=field_type,
                is_required=is_required,
                validation_rule=validation_rule or {},
            )
        )


__all__ = ["AssetCustomFieldService"]
