"""``validation_audit`` table. Per docs/043 "AUDIT": Validation
Creation, Execution, Rule Changes, Profile Changes, Result
Modifications, Administrative Operations. Class named
``ValidationAuditEntry``, not ``ValidationAudit``, matching the same
"avoid a bare-noun class name that reads like a verb/table-name
collision" precedent ``services/workflow-runtime-service``'s own
``WorkflowAuditEntry`` established.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AuditOutcome


class ValidationAuditEntry(BaseModel):
    """One privileged/administrative action recorded against validation content."""

    __tablename__ = "validation_audit"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    outcome: Mapped[AuditOutcome] = mapped_column(String(16), default=AuditOutcome.SUCCESS)
    reason: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)


__all__ = ["ValidationAuditEntry"]
