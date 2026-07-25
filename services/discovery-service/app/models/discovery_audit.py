"""``discovery_audit`` table -- the privileged-action audit trail.

Per docs/037 "AUDIT": Discovery Creation, Execution, Cancellation,
Profile Changes, Credential Usage, Inventory Synchronization,
Administrative Operations. **Zero plaintext/sensitive persistence
concern here** (like ``services/inventory-service``'s own audit trail,
unlike ``services/secrets-management-service``'s) -- ``before``/
``after`` may safely capture full field snapshots; "Credential Usage"
records only which :class:`~app.models.discovery_credential
.DiscoveryCredential` (by id/name) was used, never the resolved secret
value itself.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AuditOutcome


class DiscoveryAuditEntry(BaseModel):
    """One privileged/administrative discovery action."""

    __tablename__ = "discovery_audit"

    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("discovery_jobs.id", ondelete="SET NULL"), default=None
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    action: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[AuditOutcome] = mapped_column(String(16), default=AuditOutcome.SUCCESS)
    reason: Mapped[str] = mapped_column(String(1024), default="")
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)


__all__ = ["DiscoveryAuditEntry"]
