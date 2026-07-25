"""Response schema for ``GET /discovery/results``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import DiscoveryResultStatus, ProtocolType


class DiscoveryResultResponse(BaseModel):
    """One protocol probe's raw outcome."""

    id: UUID
    job_id: UUID
    target_id: UUID
    protocol: ProtocolType
    status: DiscoveryResultStatus
    latency_ms: float | None
    raw_data: dict[str, Any]
    error_message: str | None
    executed_at: datetime


__all__ = ["DiscoveryResultResponse"]
