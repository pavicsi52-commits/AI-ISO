"""Asset label management. Per docs/036 "LABELS": Key/Value Labels,
Namespaces, Selectors, Kubernetes Compatible Labels.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError

from app.models.asset_label import AssetLabel
from app.repositories.asset_label import AssetLabelRepository


class AssetLabelService:
    """Sets, lists, and removes key/value labels on an asset."""

    def __init__(self, labels: AssetLabelRepository) -> None:
        self._labels = labels

    async def list_for_asset(self, asset_id: UUID) -> list[AssetLabel]:
        """Every label assigned to *asset_id*."""
        return await self._labels.list_for_asset(asset_id)

    async def set(
        self,
        asset_id: UUID,
        *,
        organization_id: UUID,
        key: str,
        value: str,
        namespace: str | None = None,
    ) -> AssetLabel:
        """Set *key* to *value* (optionally within *namespace*) on *asset_id*.

        Raises:
            ConflictError: If the key already exists (use :meth:`update` to change it).
        """
        if await self._labels.get_by_key(asset_id, key, namespace=namespace) is not None:
            raise ConflictError(f"Label {key!r} already exists on this asset.")
        return await self._labels.create(
            AssetLabel(
                asset_id=asset_id,
                organization_id=organization_id,
                namespace=namespace,
                key=key,
                value=value,
            )
        )

    async def remove(self, asset_id: UUID, label_id: UUID) -> None:
        """Remove a label.

        Raises:
            NotFoundError: If no such label exists for *asset_id*.
        """
        record = await self._labels.require_by_id(label_id)
        if record.asset_id != asset_id:
            raise NotFoundError(f"Label '{label_id}' was not found for this asset.")
        await self._labels.delete(label_id)


__all__ = ["AssetLabelService"]
