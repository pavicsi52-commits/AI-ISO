"""Response schema for :class:`~app.models.configuration_audit.ConfigurationAuditEntry`."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import AuditOutcome


class ConfigurationAuditResponse(BaseModel):
    """One privileged/administrative action recorded against a configuration profile."""

    id: UUID
    profile_id: UUID | None
    actor_id: UUID | None
    action: str
    outcome: AuditOutcome
    reason: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None


__all__ = ["ConfigurationAuditResponse"]
