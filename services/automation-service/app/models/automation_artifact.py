"""``automation_artifacts`` table. Per docs/040 "ARTIFACTS" "Store":
Execution Reports, Generated Files, Playbook Outputs, Logs,
Configuration Snapshots, Validation Results, Attachments.

Automation artifacts are text/JSON (rendered reports, captured
playbook stdout, configuration snapshots), never a large opaque binary
-- :attr:`content` stores it inline rather than via a MinIO-backed
``StorageWrapper``, the same "keep the infrastructure footprint to
Postgres/Redis/RabbitMQ only" precedent
``services/configuration-management-service``'s own
``ConfigurationBackup`` established.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ArtifactType


class AutomationArtifact(BaseModel):
    """One stored artifact produced by an automation execution."""

    __tablename__ = "automation_artifacts"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("automation_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    artifact_type: Mapped[ArtifactType] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(255))
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    checksum: Mapped[str | None] = mapped_column(String(128), default=None)


__all__ = ["AutomationArtifact"]
