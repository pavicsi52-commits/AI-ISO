"""Response schema for :class:`~app.models.automation_audit.AutomationAuditEntry`."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import AuditOutcome


class AutomationAuditResponse(BaseModel):
    """One privileged/administrative action recorded against a job or execution."""

    id: UUID
    job_id: UUID | None
    execution_id: UUID | None
    actor_id: UUID | None
    action: str
    outcome: AuditOutcome
    reason: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None


__all__ = ["AutomationAuditResponse"]
