"""Request/response schemas for ``/users/contacts``."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, model_validator
from shared_core.validators.fields.contact import validate_email

from app.models.enums import ContactType
from app.validators.phone import validate_phone

_PHONE_LIKE_TYPES = frozenset({ContactType.PHONE, ContactType.MOBILE, ContactType.FAX})


class ContactCreateRequest(BaseModel):
    """Body of ``POST /users/contacts``.

    ``value``'s shape depends on ``contact_type``: a phone number for
    ``PHONE``/``MOBILE``/``FAX``, an email address for ``EMAIL`` --
    validated together rather than per-field, since neither validator
    alone knows which one applies.
    """

    contact_type: ContactType
    value: str = Field(max_length=320)
    label: str | None = Field(default=None, max_length=64)
    is_primary: bool = False

    @model_validator(mode="after")
    def _validate_value_shape(self) -> ContactCreateRequest:
        if self.contact_type in _PHONE_LIKE_TYPES:
            result = validate_phone(self.value)
        elif self.contact_type is ContactType.EMAIL:
            result = validate_email(self.value)
        else:
            return self
        if not result.valid:
            raise ValueError("; ".join(result.errors))
        return self


class ContactResponse(BaseModel):
    """One contact method."""

    id: UUID
    contact_type: ContactType
    value: str
    label: str | None
    is_primary: bool
    is_verified: bool


__all__ = ["ContactCreateRequest", "ContactResponse"]
