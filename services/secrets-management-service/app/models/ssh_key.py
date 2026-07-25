"""``ssh_key_store`` table. Per docs/035 "SSH KEY MANAGEMENT": RSA,
ECDSA, Ed25519, Key Generation, Import, Export, Fingerprint
Validation, Rotation, Expiration.

The public key (:attr:`public_key`) is plaintext -- by definition not
sensitive; the private key is stored as a
:class:`~app.models.secret.Secret` referenced by
:attr:`private_key_secret_id`, the same public/private split
``app/models/certificate.py`` uses.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import SSHKeyStatus, SSHKeyType


class SSHKey(BaseModel):
    """One SSH keypair's public material and metadata."""

    __tablename__ = "ssh_key_store"

    name: Mapped[str] = mapped_column(String(255))
    key_type: Mapped[SSHKeyType] = mapped_column(String(16), index=True)
    public_key: Mapped[str] = mapped_column(Text)
    private_key_secret_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("secret_vault.id", ondelete="CASCADE")
    )
    fingerprint: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[SSHKeyStatus] = mapped_column(
        String(16), default=SSHKeyStatus.ACTIVE, index=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["SSHKey"]
