"""Response schema for ``GET /validation/remediation``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import RemediationActionType


class ValidationRemediationResponse(BaseModel):
    """One suggested or applied fix for a validation failure."""

    id: UUID
    organization_id: UUID
    failure_id: UUID
    action_type: RemediationActionType
    description: str
    automation_job_key: str | None
    playbook_key: str | None
    workflow_key: str | None
    knowledge_base_url: str | None
    is_applied: bool
    applied_at: datetime | None
    applied_by: UUID | None


__all__ = ["ValidationRemediationResponse"]
