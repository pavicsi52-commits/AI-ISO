"""Response schema for ``GET /assets/{id}/compliance``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import ComplianceStatus, ComplianceType


class AssetComplianceResponse(BaseModel):
    """One compliance-type evaluation."""

    id: UUID
    managed_asset_id: UUID
    compliance_type: ComplianceType
    status: ComplianceStatus
    checked_at: datetime
    details: dict[str, Any]
    exception_reason: str | None


__all__ = ["AssetComplianceResponse"]
