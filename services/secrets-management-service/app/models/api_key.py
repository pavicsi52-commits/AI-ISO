"""``api_key_store`` table. Per docs/035 "API KEY MANAGEMENT": Generation,
Rotation, Expiration, Scopes, Revocation, Usage Tracking, Audit.

Stores third-party/outbound API keys (e.g. an AI provider key another
AI-IOS service needs to call out with) -- distinct from
``shared_core.security.apikey``, which issues *inbound* platform API
keys for authenticating callers into a service and is deliberately
hash-only/non-retrievable. Keys managed here must be retrievable (the
whole point is other services fetch them), so the full key value is
stored as a :class:`~app.models.secret.Secret` referenced by
:attr:`secret_id`; :attr:`key_prefix` is a short, non-sensitive preview
(e.g. ``"sk_live_ab12"``) for identification in list views without
decrypting anything.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ApiKeyStatus


class ApiKeyEntry(BaseModel):
    """One managed third-party API key."""

    __tablename__ = "api_key_store"

    name: Mapped[str] = mapped_column(String(255))
    key_prefix: Mapped[str] = mapped_column(String(32))
    secret_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("secret_vault.id", ondelete="CASCADE"))
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[ApiKeyStatus] = mapped_column(
        String(16), default=ApiKeyStatus.ACTIVE, index=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["ApiKeyEntry"]
