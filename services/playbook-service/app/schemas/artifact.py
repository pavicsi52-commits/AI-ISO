"""Response schema for playbook artifacts."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import ArtifactType


class PlaybookArtifactResponse(BaseModel):
    """One stored artifact produced from a playbook version."""

    id: UUID
    playbook_id: UUID
    version_id: UUID | None
    artifact_type: ArtifactType
    name: str
    content: dict[str, Any]
    checksum: str | None


__all__ = ["PlaybookArtifactResponse"]
