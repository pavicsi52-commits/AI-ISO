"""``secret_access`` table -- per-principal access grants on a secret.

Per docs/035 "SECRET ACCESS": Read, Write, Rotate, Delete, Export,
Share, Lease, Restore. "Integrate with Prompt 032 RBAC."

**Design decision, matching established precedent**: rather than a
live HTTP call to ``services/rbac-service`` for every access check
(the same "Integrate Prompt 032" instruction
``services/organization-service`` and ``services/project-service``
already resolved identically for their own membership models), this
table is a self-contained ACL: a secret's owner
(:attr:`~app.models.secret.Secret.owner_id`) always has full access;
every other principal needs an explicit grant here, one row per
principal listing the specific actions they're allowed
(:class:`~app.models.enums.SecretAccessAction`), optionally
time-limited via :attr:`expires_at` -- itself the mechanism "Share"
backs.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class SecretAccessGrant(BaseModel):
    """One principal's explicit access grant on a secret."""

    __tablename__ = "secret_access"
    __table_args__ = (UniqueConstraint("secret_id", "principal_id", name="uq_secret_access_grant"),)

    secret_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("secret_vault.id", ondelete="CASCADE"), nullable=False, index=True
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(index=True)
    actions: Mapped[list[Any]] = mapped_column(JSON, default=list)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["SecretAccessGrant"]
