"""``users`` table.

Per docs/030_Enterprise_Authentication_Service.md.txt "DATABASE
TABLES". Identity only -- credentials live in a separate
``user_credentials`` row (:mod:`app.models.credentials`), so a future
federated-identity user (LDAP/SAML/OAuth2, deferred per this package's
README) can exist with no password credential at all.
"""

from __future__ import annotations

from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column


class User(BaseModel):
    """A person or machine identity known to the authentication service."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), default=None)
    is_email_verified: Mapped[bool] = mapped_column(default=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["User"]
