"""Request/response schemas for ``POST /secrets/{id}/lease`` and
``DELETE /leases/{id}``. Per docs/035 "SECRET LEASING": Temporary
Credentials, Lease Duration.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import LeaseStatus


class SecretLeaseRequest(BaseModel):
    """Body of ``POST /secrets/{id}/lease``."""

    principal_id: UUID
    duration_seconds: int = Field(gt=0, le=86400)


class SecretLeaseResponse(BaseModel):
    """A newly issued (or renewed) lease, including the decrypted value
    it grants temporary access to -- a lease's entire purpose is
    "Temporary Credentials", so withholding the value here would make
    the endpoint pointless.
    """

    id: UUID
    secret_id: UUID
    principal_id: UUID
    status: LeaseStatus
    value: str
    issued_at: datetime
    expires_at: datetime
    lease_duration_seconds: int
    renewed_count: int


__all__ = ["SecretLeaseRequest", "SecretLeaseResponse"]
