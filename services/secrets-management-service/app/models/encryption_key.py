"""``encryption_keys`` table -- Data Encryption Keys (DEKs), wrapped by
the envelope-encryption master key.

Per docs/035 "ENCRYPTION": "Envelope Encryption", "Master Key", "Data
Encryption Keys". The master key itself (see
``app/config/master_key.py``) is never persisted anywhere; only DEKs
*wrapped* (encrypted) by it are stored here, in
:attr:`EncryptionKey.wrapped_key`. Rotating the master key means
re-wrapping every row here under the new master key (see
``app/models/key_rotation_history.py``); rotating a DEK means minting
a new row and re-encrypting every :class:`~app.models.secret_version
.SecretVersion` that referenced the old one.
"""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import EncryptionKeyStatus


class EncryptionKey(BaseModel):
    """One Data Encryption Key, wrapped (encrypted) by the master key."""

    __tablename__ = "encryption_keys"

    version: Mapped[int] = mapped_column(Integer, index=True)
    wrapped_key: Mapped[str] = mapped_column(Text)
    algorithm: Mapped[str] = mapped_column(String(32), default="AES-256-GCM")
    status: Mapped[EncryptionKeyStatus] = mapped_column(
        String(16), default=EncryptionKeyStatus.ACTIVE, index=True
    )


__all__ = ["EncryptionKey"]
