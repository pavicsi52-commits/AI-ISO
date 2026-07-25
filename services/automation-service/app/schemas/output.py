"""Response schema for an automation execution's own captured outputs."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AutomationOutputResponse(BaseModel):
    """One captured output value produced during an automation execution."""

    id: UUID
    execution_id: UUID
    step_id: UUID | None
    key: str
    value: Any


__all__ = ["AutomationOutputResponse"]
