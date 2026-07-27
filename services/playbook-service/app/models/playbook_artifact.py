"""``playbook_artifacts`` table -- a distributable output produced from
one playbook version (a signed package, a rendered export, a checksum
manifest), per docs/041 "REPOSITORY" "Export" and "SECURITY" "Digital
Signatures"/"Checksum Validation".

Playbook content is text/JSON, never a large opaque binary --
:attr:`content` stores it inline rather than via a MinIO-backed
``StorageWrapper``, the same "keep the infrastructure footprint to
Postgres/Redis/RabbitMQ only" precedent
``services/automation-service``'s own ``AutomationArtifact``
established.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ArtifactType


class PlaybookArtifact(BaseModel):
    """One stored artifact produced from a playbook version."""

    __tablename__ = "playbook_artifacts"

    playbook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("playbook_versions.id", ondelete="CASCADE"), default=None, index=True
    )
    artifact_type: Mapped[ArtifactType] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(255))
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    checksum: Mapped[str | None] = mapped_column(String(64), default=None)


__all__ = ["PlaybookArtifact"]
