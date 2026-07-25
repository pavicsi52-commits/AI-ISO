"""``discovery_credentials`` table -- a *reference* to credential
material, never the material itself.

Per docs/037 "SECURITY": "Credentials must be retrieved only from the
Secrets Management Service. Never persist plaintext credentials." This
row stores only :attr:`secret_id` (the corresponding
``services/secrets-management-service`` ``Secret.id``) plus enough
metadata to select the right credential for a protocol probe --
resolving the actual value always means a live call to that service at
scan time (``app/discovery/credentials.py``), never a local read.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import CredentialType, ProtocolType


class DiscoveryCredential(BaseModel):
    """A named reference to a secret held by the Secrets Management Service."""

    __tablename__ = "discovery_credentials"

    name: Mapped[str] = mapped_column(String(255), index=True)
    protocol: Mapped[ProtocolType] = mapped_column(String(16), index=True)
    credential_type: Mapped[CredentialType] = mapped_column(String(16))
    secret_id: Mapped[uuid.UUID] = mapped_column(index=True)
    username: Mapped[str | None] = mapped_column(String(255), default=None)


__all__ = ["DiscoveryCredential"]
