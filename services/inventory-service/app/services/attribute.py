"""Custom attribute *value* management, validated against a field's
own definition (``app/services/custom_field.py``). Per docs/036
"CUSTOM ATTRIBUTES": Validation, Typed Values.
"""

from __future__ import annotations

import json
from datetime import date
from uuid import UUID

from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError

from app.models.asset_attribute import AssetAttribute
from app.models.enums import CustomFieldType
from app.repositories.asset_attribute import AssetAttributeRepository
from app.repositories.asset_custom_field import AssetCustomFieldRepository


def _validate_typed_value(value: str, field_type: CustomFieldType) -> None:
    """Raise :class:`ValidationError` if *value* doesn't parse as *field_type*.

    Uses ``==``/``str()`` throughout rather than ``.value`` -- *field_type*
    is typically a freshly-``require_by_id``-loaded ORM attribute, and
    this column (like every enum-typed column across AI-IOS) is declared
    plain ``String``, not ``sqlalchemy.Enum``. SQLAlchemy's weakly-
    referenced identity map can hand back the raw string instead of a
    reconstituted enum member once the row's earlier in-memory instance
    has been garbage collected -- comparisons still work either way
    (``CustomFieldType`` is a ``StrEnum``), but ``.value`` does not, the
    same real bug ``services/secrets-management-service``'s
    ``SecretService.update()`` and this service's own
    ``app/topology/graph.py::_relationship_label`` were already caught
    and fixed for.
    """
    try:
        if field_type == CustomFieldType.INTEGER:
            int(value)
        elif field_type == CustomFieldType.FLOAT:
            float(value)
        elif field_type == CustomFieldType.BOOLEAN:
            if value.lower() not in ("true", "false"):
                raise ValueError(value)
        elif field_type == CustomFieldType.DATE:
            date.fromisoformat(value)
        elif field_type == CustomFieldType.JSON:
            json.loads(value)
    except ValueError as exc:
        raise ValidationError(f"Value {value!r} is not a valid {field_type!s}.") from exc


class AssetAttributeService:
    """Sets, lists, and removes typed custom attribute values on an asset."""

    def __init__(
        self, attributes: AssetAttributeRepository, fields: AssetCustomFieldRepository
    ) -> None:
        self._attributes = attributes
        self._fields = fields

    async def list_for_asset(self, asset_id: UUID) -> list[AssetAttribute]:
        """Every custom attribute value set on *asset_id*."""
        return await self._attributes.list_for_asset(asset_id)

    async def set(
        self, asset_id: UUID, *, organization_id: UUID, custom_field_id: UUID, value: str
    ) -> AssetAttribute:
        """Set *asset_id*'s value for *custom_field_id*, creating or
        updating as needed.

        Raises:
            NotFoundError: If no such custom field definition exists.
            ValidationError: If *value* doesn't match the field's declared type.
        """
        field = await self._fields.require_by_id(custom_field_id)
        _validate_typed_value(value, field.field_type)

        existing = await self._attributes.get_for_field(asset_id, custom_field_id)
        if existing is not None:
            existing.value = value
            return existing
        return await self._attributes.create(
            AssetAttribute(
                asset_id=asset_id,
                organization_id=organization_id,
                custom_field_id=custom_field_id,
                value=value,
            )
        )

    async def remove(self, asset_id: UUID, attribute_id: UUID) -> None:
        """Remove a custom attribute value.

        Raises:
            NotFoundError: If no such value exists for *asset_id*.
        """
        record = await self._attributes.require_by_id(attribute_id)
        if record.asset_id != asset_id:
            raise NotFoundError(f"Attribute '{attribute_id}' was not found for this asset.")
        await self._attributes.delete(attribute_id)


__all__ = ["AssetAttributeService"]
