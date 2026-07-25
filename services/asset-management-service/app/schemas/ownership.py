"""Request/response schemas for ``POST /assets/{id}/transfer`` and the
underlying :class:`~app.models.asset_owner.AssetOwner`/
:class:`~app.models.asset_contact.AssetContact` records.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.models.enums import ContactRole, OwnerRole


class OwnershipTransferRequest(BaseModel):
    """Body of ``POST /assets/{id}/transfer``."""

    role: OwnerRole
    principal_id: UUID | None = None
    name: str | None = None


class AssetOwnerResponse(BaseModel):
    """One ownership-role assignment."""

    id: UUID
    managed_asset_id: UUID
    role: OwnerRole
    principal_id: UUID | None
    name: str | None


class AssetContactResponse(BaseModel):
    """One reachable contact."""

    id: UUID
    managed_asset_id: UUID
    role: ContactRole
    name: str
    email: str | None
    phone: str | None


__all__ = ["AssetContactResponse", "AssetOwnerResponse", "OwnershipTransferRequest"]
