"""Request/response schemas for ``/ssh-keys``. Per docs/035 "SSH KEY
MANAGEMENT": Key Generation, Import, Export, Fingerprint Validation.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.models.enums import SSHKeyStatus, SSHKeyType


class SSHKeyCreateRequest(BaseModel):
    """Body of ``POST /ssh-keys``.

    Supports both "Key Generation" (omit :attr:`public_key` and
    :attr:`private_key`, a fresh keypair is generated server-side) and
    "Import" (supply both, an existing keypair is stored as-is) -- the
    single ``POST`` endpoint docs/035 lists covers both.
    """

    organization_id: UUID
    project_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    key_type: SSHKeyType
    owner_id: UUID
    expires_at: datetime | None = None
    public_key: str | None = None
    private_key: str | None = None

    @model_validator(mode="after")
    def _public_and_private_together(self) -> SSHKeyCreateRequest:
        if (self.public_key is None) != (self.private_key is None):
            raise ValueError(
                "public_key and private_key must be supplied together (import mode) "
                "or both omitted (generate mode)."
            )
        return self


class SSHKeyResponse(BaseModel):
    """One SSH keypair's public material and metadata -- never the
    private key. Used by ``GET /ssh-keys``.
    """

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    name: str
    key_type: SSHKeyType
    public_key: str
    private_key_secret_id: UUID
    fingerprint: str
    status: SSHKeyStatus
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SSHKeyCreateResponse(SSHKeyResponse):
    """The response to ``POST /ssh-keys`` only -- carries the private key
    once, at creation time, the same "shown once" pattern
    ``ApiKeyCreateResponse`` uses.
    """

    private_key: str


__all__ = ["SSHKeyCreateRequest", "SSHKeyCreateResponse", "SSHKeyResponse"]
