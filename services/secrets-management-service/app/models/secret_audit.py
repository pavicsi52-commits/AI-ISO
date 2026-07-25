"""``secret_audit`` table -- privileged-action audit trail for a secret.

Per docs/035 "AUDIT": Create, Update, Delete, Read, Decrypt, Rotate,
Lease, Export, Import, Provider Access, Administrative Operations.

**Zero plaintext persistence, absolutely no exception here**: neither
:attr:`before` nor :attr:`after` may ever contain a secret's plaintext
or even encrypted value -- only metadata (status, name, category,
version *numbers*) changes. Enforced entirely by convention in
``app/services/secret.py`` (never passed a value to snapshot), the
same "never log plaintext secrets" discipline docs/035's own
"SECURITY" section requires.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AuditOutcome


class SecretAuditEntry(BaseModel):
    """One privileged/administrative action recorded against a secret."""

    __tablename__ = "secret_audit"

    secret_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("secret_vault.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    action: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[AuditOutcome] = mapped_column(String(16), default=AuditOutcome.SUCCESS)
    reason: Mapped[str] = mapped_column(String(1024), default="")
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)


__all__ = ["SecretAuditEntry"]
