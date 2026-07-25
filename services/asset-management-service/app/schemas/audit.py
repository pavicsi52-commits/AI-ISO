"""Response schema for :class:`~app.models.asset_audit.AssetAuditEntry`."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import AuditOutcome


class AssetAuditResponse(BaseModel):
    """One privileged/administrative action recorded against a managed asset."""

    id: UUID
    managed_asset_id: UUID | None
    actor_id: UUID | None
    action: str
    outcome: AuditOutcome
    reason: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None


__all__ = ["AssetAuditResponse"]
