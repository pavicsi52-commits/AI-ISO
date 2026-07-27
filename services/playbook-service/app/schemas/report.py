"""Response schema for ``GET /playbooks/reports``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import PlaybookReportType


class PlaybookReportResponse(BaseModel):
    """One generated playbook-repository report."""

    id: UUID
    organization_id: UUID
    playbook_id: UUID | None
    report_type: PlaybookReportType
    generated_by: UUID | None
    parameters: dict[str, Any]
    result: dict[str, Any]
    generated_at: datetime


__all__ = ["PlaybookReportResponse"]
