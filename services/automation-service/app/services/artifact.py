"""Stored automation artifacts. Per docs/040 "ARTIFACTS" "Store":
Execution Reports, Generated Files, Playbook Outputs, Logs,
Configuration Snapshots, Validation Results, Attachments. Actual
artifact rows are written wherever a step produces one worth keeping;
this service owns creation and the read path
("GET /automation/executions/{id}/artifacts").
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.automation_artifact import AutomationArtifact
from app.models.enums import ArtifactType
from app.repositories.automation_artifact import AutomationArtifactRepository


class AutomationArtifactService:
    """Creates and reads artifacts produced by automation executions."""

    def __init__(self, artifacts: AutomationArtifactRepository) -> None:
        self._artifacts = artifacts

    async def list_for_execution(self, execution_id: UUID) -> list[AutomationArtifact]:
        """Every artifact recorded for *execution_id*."""
        return await self._artifacts.list_for_execution(execution_id)

    async def create(
        self,
        execution_id: UUID,
        *,
        organization_id: UUID,
        artifact_type: ArtifactType,
        name: str,
        content: dict[str, Any],
        checksum: str | None,
    ) -> AutomationArtifact:
        """Store a new artifact produced by an automation execution."""
        return await self._artifacts.create(
            AutomationArtifact(
                organization_id=organization_id,
                execution_id=execution_id,
                artifact_type=artifact_type,
                name=name,
                content=content,
                checksum=checksum,
            )
        )


__all__ = ["AutomationArtifactService"]
