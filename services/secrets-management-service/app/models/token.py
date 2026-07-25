"""``token_store`` table. Per docs/035 "TOKEN MANAGEMENT": OAuth Tokens,
Access Tokens, Refresh Tokens, Webhook Tokens, Cloud Tokens, AI
Tokens, Expiration, Rotation.

The token value itself is stored as a :class:`~app.models.secret.Secret`
referenced by :attr:`secret_id`, the same "thin metadata table
referencing the vault for sensitive material" shape
``app/models/api_key.py``/``app/models/ssh_key.py`` use.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import TokenStatus, TokenType


class TokenEntry(BaseModel):
    """One managed token."""

    __tablename__ = "token_store"

    name: Mapped[str] = mapped_column(String(255))
    token_type: Mapped[TokenType] = mapped_column(String(16), index=True)
    secret_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("secret_vault.id", ondelete="CASCADE"))
    status: Mapped[TokenStatus] = mapped_column(String(16), default=TokenStatus.ACTIVE, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["TokenEntry"]
