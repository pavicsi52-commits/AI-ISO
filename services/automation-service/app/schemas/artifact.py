"""Response schema for ``GET /automation/executions/{id}/artifacts``."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import ArtifactType


class AutomationArtifactResponse(BaseModel):
    """One stored artifact produced by an automation execution."""

    id: UUID
    execution_id: UUID
    artifact_type: ArtifactType
    name: str
    content: dict[str, Any]
    checksum: str | None


__all__ = ["AutomationArtifactResponse"]
