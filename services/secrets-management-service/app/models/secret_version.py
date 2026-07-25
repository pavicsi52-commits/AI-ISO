"""``secret_versions`` table. Per docs/035 "SECRET VERSIONING": Multiple
Versions, Rollback, Version History, Current Version, Previous
Versions.

Each row's :attr:`ciphertext` is one AES-256-GCM ``nonce || ciphertext``
blob (base64-encoded, exactly what
:func:`shared_core.security.encryption.encrypt` returns) produced by
the Data Encryption Key :attr:`encryption_key_id` references -- never
the master key directly. :attr:`Secret.current_version` (a plain
integer counter) identifies which row is "current"; :attr:`is_current`
here is a denormalized convenience flag kept in sync by
``app/services/secret.py``, so a single indexed lookup finds the
current version without also filtering by number.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column


class SecretVersion(BaseModel):
    """One encrypted version of a secret's value."""

    __tablename__ = "secret_versions"

    secret_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("secret_vault.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    encryption_key_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("encryption_keys.id"))
    ciphertext: Mapped[str] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(default=None)


__all__ = ["SecretVersion"]
