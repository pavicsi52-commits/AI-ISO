"""Request/response schemas for ``/users/addresses``."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import AddressType


class AddressCreateRequest(BaseModel):
    """Body of ``POST /users/addresses``."""

    address_type: AddressType = AddressType.HOME
    line1: str = Field(max_length=255)
    line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=128)
    state_province: str | None = Field(default=None, max_length=128)
    postal_code: str | None = Field(default=None, max_length=32)
    country: str | None = Field(default=None, max_length=2)
    is_primary: bool = False


class AddressResponse(BaseModel):
    """One address."""

    id: UUID
    address_type: AddressType
    line1: str
    line2: str | None
    city: str | None
    state_province: str | None
    postal_code: str | None
    country: str | None
    is_primary: bool


__all__ = ["AddressCreateRequest", "AddressResponse"]
